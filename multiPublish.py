#!/usr/bin/env python

import mozhttpd
import sys
import tempfile
from mozdevice import DeviceManagerSUT

autophone_host = mozhttpd.iface.get_lan_ip()

ips = sys.argv[1:]
for ip in ips:
    dm = DeviceManagerSUT(ip)
    with tempfile.NamedTemporaryFile() as f:
        ini_contents = """[Registration Server]
IPAddr = %s
PORT = 28001
HARDWARE = %s
POOL = %s""" % (autophone_host, 'panda_' + ip, dm.getInfo('id')['id'][0])
        f.write(ini_contents)
        f.flush()
        dm.pushFile(f.name,
                    '/data/data/com.mozilla.SUTAgentAndroid/files/SUTAgent.ini')
