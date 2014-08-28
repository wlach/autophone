# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import ConfigParser
import glob
import logging
import os
import time

from mozprofile import FirefoxProfile

from adb import ADBError
from adb_android import ADBAndroid as ADBDevice
from logdecorator import LogDecorator
from phonestatus import PhoneStatus

class PhoneTest(object):

    """
    The initialization function. It takes and stores all the information
    related to contacting this phone.
    Params:
    phoneid = ID of phone, to be used in log messages and reporting
    serial = serial number for adb style interfaces
    ip = phone's IP address (where sutagent running if it is running)
    sutcmdport = cmd port of sutagent if it is running
    sutdataport = data port of sutagent if it is running
    machinetype = pretty name of machine type - i.e. galaxy_nexus, droid_pro etc
    osver = version string of phone OS
    TODO: Add in connection data here for programmable power so we can add a
    powercycle method to this class.
    """
    def __init__(self, phone, options, config_file=None,
                 enable_unittests=False, test_devices_repos={}):
        self.config_file = config_file
        self.cfg = ConfigParser.RawConfigParser()
        self.cfg.read(self.config_file)
        self.enable_unittests = enable_unittests
        self.test_devices_repos = test_devices_repos
        self.update_status_cb = None
        self.phone = phone
        self.worker_subprocess = None
        self.options = options
        self.logger = logging.getLogger('autophone.phonetest')
        self.loggerdeco = LogDecorator(self.logger,
                                       {'phoneid': self.phone.id,
                                        'pid': os.getpid()},
                                       '%(phoneid)s|%(pid)s|%(message)s')
        self.loggerdeco.info('init autophone.phonetest')
        self._base_device_path = ''
        self.profile_path = '/data/local/tmp/profile'
        self._dm = None

    def _check_device(self):
        for attempt in range(self.options.phone_retry_limit):
            output = self._dm.get_state()
            if output == 'device':
                break
            self.loggerdeco.warning(
                'PhoneTest:_check_device Attempt: %d: %s' %
                (attempt, output))
            time.sleep(self.options.phone_retry_wait)
        if output != 'device':
            raise ADBError('PhoneTest:_check_device: Failed')

    @property
    def dm(self):
        if not self._dm:
            self.loggerdeco.info('PhoneTest: Connecting to %s...' % self.phone.id)
            self._dm = ADBDevice(device_serial=self.phone.serial,
                                 log_level=self.options.debug,
                                 logger_name='autophone.phonetest.adb',
                                 device_ready_retry_wait=self.options.device_ready_retry_wait,
                                 device_ready_retry_attempts=self.options.device_ready_retry_attempts)
            # Override mozlog.logger
            self._dm._logger = self.loggerdeco
            self.loggerdeco.info('PhoneTest: Connected.')
        self._check_device()
        return self._dm

    @property
    def base_device_path(self):
        if self._base_device_path:
            return self._base_device_path
        success = False
        e = None
        for attempt in range(self.options.phone_retry_limit):
            self._base_device_path = self.dm.test_root + '/autophone'
            self.loggerdeco.debug('Attempt %d creating base device path %s' % (attempt, self._base_device_path))
            try:
                if not self.dm.is_dir(self._base_device_path):
                    self.dm.mkdir(self._base_device_path, parents=True)
                success = True
                break
            except ADBError:
                self.loggerdeco.exception('Attempt %d creating base device path %s' % (attempt, self._base_device_path))
                time.sleep(self.options.phone_retry_wait)

        if not success:
            raise e

        self.loggerdeco.debug('base_device_path is %s' % self._base_device_path)

        return self._base_device_path

    @property
    def build(self):
        return self.worker_subprocess.build

    def setup_job(self, worker_subprocess):
        self.worker_subprocess = worker_subprocess
        self.logger_original = self.logger
        self.loggerdeco_original = self.loggerdeco
        self.dm_logger_original = self.dm._logger

    def run_job(self):
        raise NotImplementedError

    def teardown_job(self):
        self.worker_subprocess = None
        self.logger = self.logger_original
        self.loggerdeco = self.loggerdeco_original
        self.dm._logger = self.dm_logger_original

    def set_dm_debug(self, level):
        self.options.debug = level
        if self._dm:
            self._dm.log_level = level

    def update_status(self, phone_status=PhoneStatus.WORKING, message=None):
        if self.update_status_cb:
            self.update_status_cb(phone_status=phone_status,
                                  build=self.build,
                                  message=message)

    def install_profile(self, profile=None):
        if not profile:
            profile = FirefoxProfile()

        profile_path_parent = os.path.split(self.profile_path)[0]
        success = False
        for attempt in range(self.options.phone_retry_limit):
            try:
                self.loggerdeco.debug('Attempt %d installing profile' % attempt)
                if self.dm.is_dir(self.profile_path, root=True):
                    self.dm.rm(self.profile_path, recursive=True, root=True)
                self.dm.chmod(profile_path_parent, root=True)
                self.dm.mkdir(self.profile_path, root=True)
                self.dm.chmod(self.profile_path, root=True)
                self.dm.push(profile.profile, self.profile_path)
                self.dm.chmod(self.profile_path, recursive=True, root=True)
                success = True
                break
            except ADBError:
                self.loggerdeco.exception('Attempt %d Exception installing profile to %s' % (attempt, self.profile_path))
                time.sleep(self.options.phone_retry_wait)

        if not success:
            self.loggerdeco.error('Failure installing profile to %s' % self.profile_path)

        return success

    def run_fennec_with_profile(self, appname, url):
        self.loggerdeco.debug('run_fennec_with_profile: %s %s' % (appname, url))
        try:
            self.dm.pkill(appname, root=True)
            self.dm.launch_fennec(appname,
                                 intent="android.intent.action.VIEW",
                                 moz_env={'MOZ_CRASHREPORTER_NO_REPORT': '1'},
                                 extra_args=['--profile', self.profile_path],
                                 url=url,
                                 wait=False,
                                 fail_if_running=False)
        except:
            self.loggerdeco.exception('run_fennec_with_profile: Exception:')
            raise

    def remove_sessionstore_files(self):
        self.dm.rm(self.profile_path + '/sessionstore.js', force=True)
        self.dm.rm(self.profile_path + '/sessionstore.bak', force=True)

    def check_for_crashes(self):
        """
        Perform a quick check for crashes by checking
        self.profile_path/minidumps for dump files.

        TODO: Should use mozbase/mozcrash with symbols and minidump_stackwalk
        to process and report crashes.
        """
        if glob.glob(os.path.join(self.profile_path, 'minidumps', '*.dmp')):
            return True
        return False
