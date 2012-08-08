#!/usr/bin/env python

from optparse import OptionParser
import json
import os
import subprocess
import sys
import time

def rm_f(fname):
    '''Like unlink, but ignores exception if file doesn't already exist'''
    try:
        os.unlink(fname)
    except OSError:
        pass

def get_num_lines(fname):
    try:
        return len(open(fname).readlines())
    except IOError:
        return 0

def run(args=sys.argv[1:]):
    parser = OptionParser()
    parser.add_option("-n", "--num-runs", action="store", default=1,
                      type = "int", dest = "num_runs",
                      help = "Number of runs to use")
    parser.add_option('--cache', action='store', type='string', dest='cachefile',
                      default='autophone_cache.json',
                      help='Cache file to use, defaults to autophone_cache.json '
                      'in local dir')

    (options, args) = parser.parse_args(args)

    if options.num_runs < 1:
        print "Number of runs (%s) should be at least 1!" % options.num_runs
        sys.exit(1)

    rm_f('smoketest_pass')
    rm_f('smoketest_fail')

    autophone_process = subprocess.Popen(["python", "autophone.py",
                                          "--disable-pulse", "--cache", options.cachefile,
                                          "-t", "tests/smoketest_manifest.ini"])

    for i in range(options.num_runs):
        subprocess.check_call(["python", "trigger_runs.py", "latest"])

    try:
        cache_json = json.loads(open(options.cachefile).read())
    except ValueError:
        print "Unable to find any registered phones! Maybe you need to run autophone standalone to let the registration process finish?"
        autophone_process.kill()
        sys.exit(1)

    num_phones = len(cache_json.get('phones'))
    num_expected = num_phones * options.num_runs

    try:
        while (get_num_lines('smoketest_pass') + get_num_lines('smoketest_fail')) < num_expected:
            time.sleep(5)
    except KeyboardInterrupt:
        print "Aborted. Killing autophone server."
        autophone_process.kill()
        sys.exit(1)

    retcode = 0

    if get_num_lines('smoketest_fail') > 0:
        print "Finished, but some failed. Summary:"
        print open('smoketest_fail').readlines()
        retcode = 1
    else:
        print "Finished, everything succeeded. Yay!"

    autophone_process.kill()

    sys.exit(retcode)

if __name__ == '__main__':
    run()
