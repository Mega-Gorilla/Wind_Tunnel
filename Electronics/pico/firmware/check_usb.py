"""Pi-side, bounded commissioning check; never sends a fan-run command."""
import json, time, datetime, sys
from pathlib import Path
import serial
PORT='/dev/serial/by-id/usb-MicroPython_Board_in_FS_mode_e660583883976d2d-if00'
results={"time":datetime.datetime.now(datetime.timezone.utc).isoformat(),"port":PORT,"exchanges":[]}
with serial.Serial(PORT,115200,timeout=0.2,write_timeout=2,exclusive=True) as ser:
    def exchange(request,expected_ok=True):
        ser.write((json.dumps(request)+'\n').encode())
        end=time.monotonic()+5
        line=b''
        while time.monotonic()<end:
            line+=ser.read(1)
            if line.endswith(b'\n'):
                response=json.loads(line)
                assert response.get('id')==request['id'], response
                assert response['ok']==expected_ok, response
                results['exchanges'].append({'request':request,'response':response})
                return response
        raise TimeoutError(repr(line))
    try:
        first=exchange({'cmd':'status','id':0})
        assert first['status']['gp16_level']==0
        assert first['status']['fan_enabled'] is False
        print(json.dumps(first),flush=True)
        for i in range(1,4):
            response=exchange({'cmd':'scan','id':i})
            print(json.dumps(response),flush=True)
        rejected=exchange({'cmd':'unsupported_probe','id':4},False)
        for i in range(5,25):
            response=exchange({'cmd':'status','id':i})
            assert response['boot_id']==first['boot_id']
            assert response['status']['gp16_level']==0
            assert response['status']['fan_enabled'] is False
            time.sleep(0.1)
        stopped=exchange({'cmd':'stop','id':25})
        print('USB CHECK: 26 matched responses; 3 scans; GP16 low; unknown command rejected.')
        results['transport_pass']=True
    finally:
        output=Path(__file__).with_name('commissioning_result.json')
        output.write_text(json.dumps(results,indent=2)+'\n')
        print('RESULT',output)
