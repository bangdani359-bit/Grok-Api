from re        import findall, search
from json      import load, dump
from base64    import b64decode
from typing    import Optional
from curl_cffi import requests
from core      import Utils
from os        import path

class Parser:
    
    mapping: dict = {}
    _mapping_loaded: bool = False
    
    grok_mapping: list = []
    _grok_mapping_loaded: bool = False
    
    @classmethod
    def _load__xsid_mapping(cls):
        if not cls._mapping_loaded and path.exists('core/mapping.json'):
            with open('core/mapping.json', 'r') as f:
                cls.mapping = load(f)
            cls._mapping_loaded = True
            
    @classmethod
    def _load_grok_mapping(cls):
        if not cls._grok_mapping_loaded and path.exists('core/grok.json'):
            with open('core/grok.json', 'r') as f:
                cls.grok_mapping = load(f)
            cls._grok_mapping_loaded = True
    
    @staticmethod
    def parse_values(html: str, loading: str = "loading-x-anim-0", scriptId: str = "") -> tuple[str, Optional[str]]:

        Parser._load__xsid_mapping()
        
        all_d_values = findall(r'"d":"(M[^"]{200,})"', html)
        svg_data = all_d_values[int(loading.split("loading-x-anim-")[1])]
        
        if scriptId:
            
            if scriptId == "ondemand.s":
                script_link: str = 'https://abs.twimg.com/responsive-web/client-web/ondemand.s.' + Utils.between(html, f'"{scriptId}":"', '"') + 'a.js'
            else:
                script_link: str = f'https://grok.com/_next/{scriptId}'

            if script_link in Parser.mapping:
                numbers: list = Parser.mapping[script_link]
                
            else:
                script_content: str = requests.get(script_link, impersonate="chrome136").text
                numbers: list = [int(x) for x in findall(r'x\[(\d+)\]\s*,\s*16', script_content)]
                Parser.mapping[script_link] = numbers
                with open('core/mapping.json', 'w') as f:
                    dump(Parser.mapping, f)

            return svg_data, numbers

        else:
            return svg_data

    
    @staticmethod
    def get_anim(html:  str, verification: str = "grok-site-verification") -> tuple[str, str]:
        
        verification_token: str = Utils.between(html, f'"name":"{verification}","content":"', '"')
        array: list = list(b64decode(verification_token))
        anim: str = "loading-x-anim-" + str(array[5] % 4)

        return verification_token, anim
    
    @staticmethod
    def parse_grok(scripts: list) -> tuple[list, str]:
        
        Parser._load_grok_mapping()
        
        for index in Parser.grok_mapping:
            if index.get("action_script") in scripts:
                return index["actions"], index["xsid_script"]
            
        # ensure variables exist even if matching scripts aren't found
        script_content1: str = ""
        script_content2: str = ""
        action_script: str = ""

        for script in scripts:
            content: str = requests.get(f'https://grok.com{script}', impersonate="chrome136").text
            if "anonPrivateKey" in content:
                script_content1 = content
                action_script = script
            elif "880932)" in content:
                script_content2 = content

        # if we didn't find the needed script parts, bail with a helpful message
        if not script_content1 or not script_content2:
            print("[parser] Failed to locate expected script contents while parsing grok scripts")
            return [], ""

        actions: list = findall(r'createServerReference\)\("([a-f0-9]+)"', script_content1)

        # Newer Grok bundles use a TurboPack push structure. Example snippet:
        # (globalThis.TURBOPACK||[]).push([..., a=>{ a.v(s=>Promise.all(["static/chunks/xxx.js"].map(...)).then(()=>s(880932))) }, ...])
        # The static chunk filename appears in an array earlier than the numeric id
        # (880932). We'll extract all chunk filenames with positions and pick the
        # one that appears most closely before the 880932 marker.
        from re import finditer as _finditer

        chunk_matches = [(mo.group(1), mo.start()) for mo in _finditer(r'["\'](static/chunks/[^"\']+\.js)["\']', script_content2)]
        pos880 = script_content2.find('880932')

        if pos880 == -1 or not chunk_matches:
            snippet = script_content2[:1000]
            print(f"[parser] xsid script regex did not match. snippet=\n{snippet}\n...")
            return [], ""

        # pick the chunk whose position is the largest but still before pos880
        candidates = [c for c in chunk_matches if c[1] < pos880]
        if candidates:
            xsid_script = max(candidates, key=lambda x: x[1])[0]
        else:
            # fallback: take the first chunk found
            xsid_script = chunk_matches[0][0]
        
        if actions and xsid_script:
            Parser.grok_mapping.append({
                "xsid_script": xsid_script,
                "action_script": action_script,
                "actions": actions
            })
            
            with open('core/grok.json', 'w') as f:
                dump(Parser.grok_mapping, f, indent=2)
                
            return actions, xsid_script
        else:
            print("Something went wrong while parsing script and actions")
        
        