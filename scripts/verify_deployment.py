"""Authenticated live smoke test for local or Docker deployment, without secrets in output."""
import os,sys,uuid,time
import httpx
def verify(base):
    with httpx.Client(base_url=base,timeout=180) as c:
        c.get('/health').raise_for_status()
        r=c.post('/api/v1/auth/login',json={'username':'admin','password':os.environ['BOOTSTRAP_PASSWORD']});r.raise_for_status()
        c.headers['Authorization']='Bearer '+r.json()['access_token']
        for path in ['processes','dashboard','agents/graph','models','audit/logs']:
            r=c.get('/api/v1/'+path);r.raise_for_status()
        assert c.get('/api/v1/audit/logs').json()['integrity_verified']
        print('Authenticated API, domain registry, graph and audit chain: passed')
        # Read-only by default; avoid adding duplicate seed data or altering user reviews.
        return True
if __name__=='__main__':verify(sys.argv[1] if len(sys.argv)>1 else 'http://127.0.0.1:8010')
