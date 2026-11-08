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
