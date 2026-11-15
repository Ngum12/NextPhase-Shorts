"""Linux decoder samples: explicit lower-bound CPU and sampled RSS, never GPU guesses."""
import os
from pathlib import Path

class DecoderSamples:
    def __init__(self):self.cpu=0.;self.rss=0;self.seen=False
    def sample(self,pid):
        try:
            # Last ')' handles spaces/parentheses in comm; PID is our own child.
            fields=Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()
            self.cpu=max(self.cpu,(int(fields[11])+int(fields[12]))/os.sysconf('SC_CLK_TCK'))
            self.rss=max(self.rss,int(fields[21])*os.sysconf('SC_PAGE_SIZE'));self.seen=True
        except (OSError,ValueError,IndexError):pass
    def attributes(self):
        return {'cpu_seconds_lower_bound':self.cpu,'rss_bytes_sampled_max':self.rss} if self.seen else {}


class EncodeProgress:
    """Bounded numeric progress; raw bytes are never logged or persisted."""
    def __init__(self):
        self.pending=b'';self.dropping=False;self.values={}

    def feed(self,chunk):
        data=self.pending+chunk;self.pending=b''
        if self.dropping:
            end=data.find(b'\n')
            if end<0:return
            data=data[end+1:];self.dropping=False
        lines=data.split(b'\n')
        for line in lines[:-1]:
            if len(line)>128:continue
            try:
                key,value=line.strip().split(b'=',1)
                if key==b'frame' and value.isdigit():
                    number=int(value)
                    if 0<=number<=1800:self.values['frames']=max(number,self.values.get('frames',0))
                elif key==b'fps':
                    number=float(value)
                    if 0<=number<=10000:self.values['frames_per_second']=number
            except (ValueError,OverflowError):pass
        if len(lines[-1])<=128:self.pending=lines[-1]
        else:self.dropping=True

    def attributes(self):return dict(self.values)
