"""Record the actual Chrome desktop; freeze frames if another app takes focus."""
from desktop_ops import *
import subprocess
import shutil
from PIL import ImageDraw

STATE=ROOT/'recording.json'
STOP=ROOT/'stop-recording'
OUT=ROOT/'real-chrome-recording.mp4'
STOP.unlink(missing_ok=True)
focus()
hwnd=chrome_window()
fps=20
log=(ROOT/'recorder-ffmpeg.log').open('w',encoding='utf-8')
cmd=[shutil.which('ffmpeg'),'-hide_banner','-y','-f','rawvideo','-pixel_format','rgb24',
     '-video_size','1920x1080','-framerate',str(fps),'-i','pipe:0','-an','-c:v','libx264',
     '-preset','veryfast','-crf','19','-pix_fmt','yuv420p','-movflags','+faststart',str(OUT)]
proc=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=log,
                      creationflags=subprocess.CREATE_NO_WINDOW)
start=time.time();state={'started_at':start,'output':str(OUT),'fps':fps,'hwnd':hwnd}
STATE.write_text(json.dumps(state),encoding='utf-8')
print(json.dumps(state),flush=True)
frame=None;count=0;frozen=0
try:
    while not STOP.exists():
        fg=win32gui.GetForegroundWindow()
        if fg==hwnd or (win32gui.GetWindowText(fg) in ('打开','Open') and win32gui.GetWindow(fg,win32con.GW_OWNER)==hwnd):
            frame=ImageGrab.grab(bbox=(0,60,2560,1500)).convert('RGB').resize((1920,1080))
            x,y=win32api.GetCursorPos();x=round(x*.75);y=round((y-60)*.75)
            if 0<=x<1920 and 0<=y<1080:
                ImageDraw.Draw(frame).polygon([(x,y),(x+1,y+22),(x+7,y+17),(x+12,y+25),(x+16,y+23),(x+11,y+15),(x+19,y+14)],fill='white',outline='#243b32',width=1)
        else:
            frozen+=1
        if frame is None:
            time.sleep(.1);continue
        proc.stdin.write(frame.tobytes());count+=1
        delay=start+count/fps-time.time()
        if delay>0:time.sleep(delay)
finally:
    proc.stdin.close();proc.wait(timeout=45);log.close()
    state.update(frames=count,duration=count/fps,wall_seconds=time.time()-start,frozen_frames=frozen,exit_code=proc.returncode)
    STATE.write_text(json.dumps(state,indent=2),encoding='utf-8')
    print(json.dumps(state),flush=True)

