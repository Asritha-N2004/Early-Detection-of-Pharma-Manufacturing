"""Run python -m backend.worker; scale against PostgreSQL only."""
import time,uuid,logging
from .app.main import init,simulation_tick
from .app.jobs import work_once
def main():
    init();owner=uuid.uuid4().hex
    while True:
        try:
            simulation_tick()
            if not work_once(owner):time.sleep(1)
        except KeyboardInterrupt:break
        except Exception:
            logging.getLogger('pharmasignal').exception('Background worker failed; retrying poll');time.sleep(2)
if __name__=='__main__':main()
