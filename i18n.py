# -*- coding: utf-8 -*-
import json, os
class I18nManager:
    def __init__(self, root_dir, default_language="en"):
        self.locales_dir=os.path.join(root_dir,"locales"); self.default_language=default_language; self.reload(); self.language=default_language
    def reload(self):
        self.catalogs={}; self.metadata={}; self.load_errors=[]
        if not os.path.isdir(self.locales_dir):
            self.load_errors.append("Locales directory not found: {}".format(self.locales_dir))
            return
        for filename in sorted(os.listdir(self.locales_dir)):
            if not filename.endswith(".json") or filename.startswith("_"): continue
            try:
                with open(os.path.join(self.locales_dir,filename),encoding="utf-8") as f: data=json.load(f)
                code=data.get("code",filename[:-5]); self.catalogs[code]=data.get("messages",{}); self.metadata[code]=data
            except Exception as exc:
                self.load_errors.append("{}: {}: {}".format(filename, type(exc).__name__, exc))
    def set_language(self,code): self.language=code if code in self.catalogs else self.default_language; return self.language
    def get(self,key,default=None): return self.catalogs.get(self.language,{}).get(key,self.catalogs.get(self.default_language,{}).get(key,default if default is not None else key))
    def source_for(self,text):
        if text in self.catalogs.get(self.default_language,{}): return text
        for cat in self.catalogs.values():
            for source,value in cat.items():
                if value==text: return source
        return text
    def language_names(self): return [(c,self.metadata[c].get("native_name",c)) for c in sorted(self.catalogs)]
    def diagnostics(self):
        """Read-only info for the Settings dialog: which locales loaded
        successfully, where from, and any files that failed to parse."""
        return {
            "available": sorted(self.catalogs.keys()),
            "locales_dir": self.locales_dir,
            "errors": list(getattr(self, "load_errors", [])),
        }

