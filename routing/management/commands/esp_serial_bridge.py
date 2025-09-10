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
                         # 1) 상태 ACK
                        ser.write((status_str + "\n").encode())
                        
                            # 2) 모든 층 방향정보 라인 전송: "1F (u,v,d), ...", "2F ...", "3F ..."
                        for lvl in (1, 2, 3):
            # 최초엔 last_result가 없을 수 있으니 보장
                            fl = Floor.objects.get(level=lvl)
                            st, _ = FloorState.objects.get_or_create(floor=fl)
                            if not st.last_result:
                                st.last_result = distances_all(level=lvl)
                                st.save(update_fields=['last_result', 'updated_at'])
                            out_line = floor_edge_dirs_line(lvl) + "\n"
                            ser.write(out_line.encode())
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