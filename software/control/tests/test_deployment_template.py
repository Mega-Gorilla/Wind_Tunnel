"""Check portable autostart commands without starting services or hardware."""
import configparser
from pathlib import Path
import shlex


def test_desktop_autostart_has_no_user_path_and_preserves_session_setup():
    deploy = Path(__file__).parents[1] / 'deploy' / 'pi'
    config = configparser.ConfigParser(interpolation=None)
    config.read(deploy / 'windtunnel-kiosk.desktop', encoding='utf-8')
    command = shlex.split(config['Desktop Entry']['Exec'])
    assert command[:2] == ['/bin/sh', '-ec']
    assert len(command) == 3
    assert '/home/' not in command[2]
    helper = (deploy / 'start-kiosk.sh').read_text(encoding='utf-8')
    expected = [line for line in helper.splitlines()
                if line.startswith(('systemctl ', 'exec systemctl '))]
    assert command[2].split('; ') == expected
