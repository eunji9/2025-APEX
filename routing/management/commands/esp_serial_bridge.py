import sys
import time
from django.core.management.base import BaseCommand, CommandError
from routing.services import apply_esp_code
from routing.services import apply_esp_code, floor_edge_dirs_line, distances_all
from routing.models import Floor, FloorState

class Command(BaseCommand):
    help = "Listen to ESP32 over serial (USB). On receiving '1'|'2'|'3', update graph state and compute distances. Sends 'ok' or 'no_change' back."

    def add_arguments(self, parser):
        parser.add_argument('--port', required=True, help="Serial port (e.g., COM3 on Windows, /dev/ttyUSB0 or /dev/ttyACM0 on Linux, /dev/tty.usbserial-xxx on macOS)")
        parser.add_argument('--baud', type=int, default=115200)

    def handle(self, *args, **opts):
        port = opts['port']; baud = opts['baud']
        try:
            import serial
        except ImportError:
            raise CommandError("pyserial not installed. Run: pip install pyserial")

        try:
            ser = serial.Serial(port, baudrate=baud, timeout=1)
        except Exception as e:
            raise CommandError(f"Failed to open {port}: {e}")

        self.stdout.write(self.style.SUCCESS(f"[serial] opened {port} @ {baud}"))
        try:
            while True:
                try:
                    raw = ser.readline()
                except Exception as e:
                    self.stderr.write(f"[serial] read error: {e}")
                    time.sleep(0.5)
                    continue

                if not raw:
                    continue

                line = raw.decode(errors='ignore').strip()
                if not line:
                    continue

                if line in ('1', '2', '3', '4', '5', '6'):
                    res = apply_esp_code(line)
                    status_str = res.get("status", "invalid")
                    try:
                        # 🔄 아두이노로 보낼 페이로드: (층, from, to) 배열만 전송(JSON 한 줄)
                        for lvl in (1, 2, 3):
                            fl = Floor.objects.get(level=lvl)
                            st, _ = FloorState.objects.get_or_create(floor=fl)
                            if not st.last_result:
                                st.last_result = distances_all(level=lvl)
                                st.save(update_fields=['last_result', 'updated_at'])

                            triples = []
                            dirs = (st.last_result or {}).get('all_edges_dir', [])
                            for u, v, d in dirs:
                                # 타입 정규화(문자/숫자/불리언 모두 안전)
                                u_i = int(str(u).strip())
                                v_i = int(str(v).strip())
                                #ds  = str(d).strip().lower()
                                #d_i = 1 if ds in ('1', 'true', 't') else 0
                                # d==0: u→v (정방향), d==1: v→u (역방향 → 뒤집기)
                                #from_n, to_n = (u_i, v_i) if d_i == 0 else (v_i, u_i)#
                                triples.append([lvl, v_i, u_i])
                            payload = ','.join(f'[{a},{b},{c}]' for a,b,c in triples)
                            ser.write((payload + ",").encode())
                            ser.flush()
                            time.sleep(0.1)
                    except Exception as e:
                        self.stderr.write(f"[serial] write error: {e}")

                    self.stdout.write(f"[serial] code={line} -> {status_str}")
                else:
                    self.stdout.write(f"[serial] ignore: '{line}'")
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("\n[serial] stopped by user"))
        finally:
            try:
                ser.close()
            except Exception:
                pass