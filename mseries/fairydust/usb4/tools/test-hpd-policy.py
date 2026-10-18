#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only OR MIT
"""Compile E1's actual HPD worker and test its physical/tunnel failure boundary."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

source = Path(sys.argv[1]).resolve()
text = (source/'drivers/gpu/drm/apple/dptxep.c').read_text()
start = text.index('static void dptxport_hpd_work(struct work_struct *work)')
end = text.index('static int dptxport_hpd_notify(', start)
worker = text[start:end]
prelude = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <errno.h>
#include <stdio.h>
struct work_struct { int unused; };
struct mutex { int held; };
struct completion { int calls; };
struct phy { int unused; };
struct apple_dcp { bool dp_tunnel; void *dev; };
struct epic_ep { struct apple_dcp *dcp; };
struct apple_epic_service { struct epic_ep *ep; };
struct dptx_port {
 struct work_struct hpd_work;
 struct mutex phy_lock;
 struct phy *atcphy;
 bool phy_initialized, tearing_down;
 struct apple_epic_service *service;
 int link_error;
 struct completion linkcfg_completion;
};
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x,v) ((x)=(v))
#define dev_info(...) ((void)0)
static void mutex_lock(struct mutex *m) { assert(m->held==0); m->held=1; }
static void mutex_unlock(struct mutex *m) { assert(m->held==1); m->held=0; }
static void complete_all(struct completion *c) { ++c->calls; }
static int read_result, set_result, read_calls, set_calls, last_hpd;
static struct dptx_port *cancel_on_read;
static int apple_dpin_get_hpd(struct phy *p) {
 assert(p); ++read_calls;
 if(cancel_on_read) cancel_on_read->tearing_down=true;
 return read_result;
}
static int dptxport_set_hpd(struct apple_epic_service *s, bool hpd) {
 assert(s); ++set_calls; last_hpd=hpd; return set_result;
}
'''
checks = r'''
int main(void) {
 struct apple_dcp dcp={0}; struct epic_ep ep={.dcp=&dcp};
 struct apple_epic_service service={.ep=&ep}; struct phy phy={0};
 for(int tunnel=0;tunnel<2;tunnel++) {
  dcp.dp_tunnel=tunnel;
  for(int failure=0;failure<3;failure++) {
   struct dptx_port port={.service=&service,.atcphy=&phy,.phy_initialized=true};
   read_result=failure==1?-EIO:1; set_result=failure==2?-ETIMEDOUT:0;
   read_calls=set_calls=0;
   dptxport_hpd_work(&port.hpd_work);
   assert(read_calls==1 && set_calls==1);
   assert(last_hpd==(failure==1?0:1));
   assert(port.linkcfg_completion.calls==(!tunnel && failure!=0));
   assert(port.link_error==(!tunnel?(failure==1?-EIO:failure==2?-ETIMEDOUT:0):0));
   assert(!port.phy_lock.held);
  }
 }
 struct dptx_port port={.service=&service,.atcphy=&phy};
 read_calls=set_calls=0;
 dptxport_hpd_work(&port.hpd_work);
 assert(read_calls==0 && set_calls==0);
 port.phy_initialized=true; cancel_on_read=&port;
 dptxport_hpd_work(&port.hpd_work);
 assert(read_calls==1 && set_calls==0);
 puts("PASS: 8 production HPD policy groups (physical/tunnel errors, no PHY, teardown)");
}
'''
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory)
    (path/'hpd.c').write_text(prelude+worker+checks)
    subprocess.run([os.environ.get('CC','cc'), '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                    '-fsanitize=undefined', str(path/'hpd.c'), '-o', str(path/'hpd')], check=True)
    subprocess.run([str(path/'hpd')], check=True)
