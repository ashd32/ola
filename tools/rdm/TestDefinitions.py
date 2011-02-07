#!/usr/bin/python
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU Library General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.
#
# TestDefinitions.py
# Copyright (C) 2010 Simon Newton

'''This defines all the tests for RDM responders.'''

__author__ = 'nomis52@gmail.com (Simon Newton)'

import datetime
import struct
from ResponderTest import ExpectedResult, ResponderTest
from ResponderTest import SupportedParamResponderTest, TestCategory
from ola import PidStore
from ola.PidStore import ROOT_DEVICE
from ola.OlaClient import RDMNack
import TestMixins

MAX_DMX_ADDRESS = 512
MAX_LABEL_SIZE = 32
MAX_PERSONALITY_NUMBER = 255

# Device Info tests
#------------------------------------------------------------------------------
class DeviceInfoTest(object):
  """The base device info test class."""
  PID = 'DEVICE_INFO'

  FIELDS = ['device_model', 'product_category', 'software_version',
            'dmx_footprint', 'current_personality', 'personality_count',
            'dmx_start_address', 'sub_device_count', 'sensor_count']
  FIELD_VALUES = {
      'protocol_major': 1,
      'protocol_minor': 0,
  }


class GetDeviceInfo(ResponderTest, DeviceInfoTest):
  """GET device info & verify."""
  CATEGORY = TestCategory.CORE

  PROVIDES = [
      'dmx_start_address',
      'current_personality',
      'dmx_footprint',
      'personality_count',
      'sub_device_count',
  ]

  def Test(self):
    self.AddExpectedResults(self.AckResponse(self.FIELDS, self.FIELD_VALUES))
    self.SendGet(ROOT_DEVICE, self.pid)

  def VerifyResult(self, unused_status, fields):
    """Check the footprint, personalities & sub devices."""
    for property in self.PROVIDES:
      self.SetPropertyFromDict(fields, property)

    footprint = fields['dmx_footprint']
    if footprint > MAX_DMX_ADDRESS:
      self.AddWarning('DMX Footprint of %d, was more than 512' % footprint)
    if footprint > 0:
      personality_count = fields['personality_count']
      current_personality = fields['current_personality']
      if personality_count == 0:
        self.AddAdvisory('DMX Footprint non 0, but no personalities listed')
      if current_personality == 0:
        self.AddWarning('Current personality should be >= 1, was %d' %
                        current_personality)
      elif current_personality > personality_count:
        self.AddWarning('Current personality (%d) should be less than the '
                        'personality count (%d)' %
                        (current_personality, personality_count))

    sub_devices = fields['sub_device_count']
    if sub_devices > 512:
      self.AddWarning('Sub device count > 512, was %d' % sub_devices)


class GetDeviceInfoWithData(ResponderTest, DeviceInfoTest):
  """GET device info with param data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS

  def Test(self):
    self.AddExpectedResults([
      self.NackResponse(RDMNack.NR_FORMAT_ERROR),
      self.AckResponse(
        self.FIELDS,
        self.FIELD_VALUES,
        warning='Get %s with data returned an ack' % self.pid.name)
    ])
    self.SendRawGet(ROOT_DEVICE, self.pid, 'foo')


class SetDeviceInfo(ResponderTest, DeviceInfoTest):
  """SET device info."""
  CATEGORY = TestCategory.ERROR_CONDITIONS

  def Test(self):
    self.AddExpectedResults(TestMixins.GetUnsupportedNacks(self.pid))
    self.SendRawSet(ROOT_DEVICE, self.pid)


class AllSubDevicesDeviceInfo(ResponderTest, DeviceInfoTest):
  """Send a Get Device Info to ALL_SUB_DEVICES."""
  CATEGORY = TestCategory.SUB_DEVICES
  def Test(self):
    self.AddExpectedResults(
        self.NackResponse(RDMNack.NR_SUB_DEVICE_OUT_OF_RANGE))
    self.SendGet(PidStore.ALL_SUB_DEVICES, self.pid)


# Supported Parameters Tests & Mixin
#------------------------------------------------------------------------------
class GetSupportedParameters(ResponderTest):
  """GET supported parameters."""
  CATEGORY = TestCategory.CORE
  PID = 'SUPPORTED_PARAMETERS'
  PROVIDES = ['manufacturer_parameters', 'supported_parameters']

  # declaring support for any of these is a warning:
  MANDATORY_PIDS = ['SUPPORTED_PARAMETERS',
                    'PARAMETER_DESCRIPTION',
                    'DEVICE_INFO',
                    'SOFTWARE_VERSION_LABEL',
                    'DMX_START_ADDRESS',
                    'IDENTIFY_DEVICE']

  # Banned PIDs, these are pid values that can not appear in the list of
  # supported parameters (these are used for discovery)
  BANNED_PID_VALUES = [1, 2, 3]

  # If responders support any of the pids in these groups, the should really
  # support all of them.
  PID_GROUPS = [
      ('LANGUAGE_CAPABILITIES', 'LANGUAGE'),
      ('DMX_PERSONALITY', 'DMX_PERSONALITY_DESCRIPTION'),
      ('SENSOR_DEFINITION', 'SENSOR_VALUE'),
      ('SELF_TEST_DESCRIPTION', 'PERFORM_SELF_TEST'),
  ]

  # If the first pid in each group is supported, the remainer of the group
  # must be.
  PID_DEPENDENCIES = [
      ('RECORD_SENSORS', 'SENSOR_VALUE'),
      ('DEFAULT_SLOT_VALUE', 'SLOT_DESCRIPTION'),
  ]

  def Test(self):
    self.AddExpectedResults([
      # TODO(simon): We should cross check this against support for anything
      # more than the required set of parameters at the end of all tests.
      self.NackResponse(RDMNack.NR_UNKNOWN_PID),
      self.AckResponse(),
    ])
    self.SendGet(ROOT_DEVICE, self.pid)

  def VerifyResult(self, status, fields):
    if not status.WasSuccessfull():
      self.SetProperty('manufacturer_parameters', [])
      self.SetProperty('supported_parameters', [])
      return

    mandatory_pids = {}
    for p in self.MANDATORY_PIDS:
      pid = self.LookupPid(p)
      mandatory_pids[pid.value] = pid

    supported_parameters = []
    manufacturer_parameters = []

    for item in fields['params']:
      param_id = item['param_id']
      if param_id in self.BANNED_PID_VALUES:
        self.AddWarning('%d listed in supported parameters' % param_id)
        continue

      if param_id in mandatory_pids:
        self.AddAdvisory('%s listed in supported parameters' %
                         mandatory_pids[param_id].name)
        continue

      supported_parameters.append(param_id)
      if param_id >= 0x8000 and param_id < 0xffe0:
        manufacturer_parameters.append(param_id)

    self.SetProperty('manufacturer_parameters', manufacturer_parameters)
    self.SetProperty('supported_parameters', supported_parameters)

    pid_store = PidStore.GetStore()

    for pid_names in self.PID_GROUPS:
      supported_pids = []
      unsupported_pids = []
      for pid_name in pid_names:
        pid = self.LookupPid(pid_name)
        if pid.value in supported_parameters:
          supported_pids.append(pid_name)
        else:
          unsupported_pids.append(pid_name)

      if supported_pids and unsupported_pids:
        self.AddAdvisory(
            '%s supported but %s is not' %
            (','.join(supported_pids), ','.join(unsupported_pids)))

    for pid_names in self.PID_DEPENDENCIES:
      if self.LookupPid(pid_names[0]).value not in supported_parameters:
        continue

      unsupported_pids = []
      for pid_name in pid_names[1:]:
        pid = self.LookupPid(pid_name)
        if pid.value not in supported_parameters:
          unsupported_pids.append(pid_name)
      if unsupported_pids:
        self.AddAdvisory('%s supported but %s is not' %
                         (pid_names[0], ','.join(unsupported_pids)))


class GetSupportedParametersWithData(ResponderTest):
  """GET supported parameters with param data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'SUPPORTED_PARAMETERS'

  def Test(self):
    self.AddExpectedResults([
      self.NackResponse(RDMNack.NR_FORMAT_ERROR),
      self.AckResponse(
        warning='Get %s with data returned an ack' % self.pid.name)
    ])
    self.SendRawGet(ROOT_DEVICE, self.pid, 'foo')


class SetSupportedParameters(ResponderTest):
  """Attempt to SET supported parameters."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'SUPPORTED_PARAMETERS'

  def Test(self):
    self.AddExpectedResults(TestMixins.GetUnsupportedNacks(self.pid))
    self.SendRawSet(ROOT_DEVICE, self.pid)


# Sub Devices Test
#------------------------------------------------------------------------------
class FindSubDevices(ResponderTest):
  """Locate the sub devices by sending DEVICE_INFO messages."""
  CATEGORY = TestCategory.SUB_DEVICES
  PID = 'DEVICE_INFO'
  PROVIDES = ['sub_device_indices']
  REQUIRES = ['sub_device_count']

  def Test(self):
    self._device_count = self.Property('sub_device_count')
    self._sub_devices = []  # stores the sub device indices
    self._current_index = 0  # the current sub device we're trying to query
    self._CheckForSubDevice()

  def _CheckForSubDevice(self):
    # For each supported param message we should either see a sub device out of
    # range or an ack
    if len(self._sub_devices) == self._device_count:
      if self._device_count == 0:
        self.SetNotRun(' No sub devices declared')
      self.SetProperty('sub_device_indices', self._sub_devices)
      self.Stop()
      return

    if self._current_index >= PidStore.MAX_VALID_SUB_DEVICE:
      self.SetFailed('Only found %d of %d sub devices' %
                     (len(self._sub_devices), self._device_count))
      self.Stop()
      return

    self.AddExpectedResults([
      self.NackResponse(RDMNack,NR_SUB_DEVICE_OUT_OF_RANGE,
                        action=self._CheckForSubDevice),
      self.AckResponse(action=self._CheckForSubDevice)
    ])
    self._current_index += 1
    self.SendGet(self._current_index, self.pid)

  def VerifyResult(self, status, fields):
    if status.WasSuccessfull():
      self._sub_devices.append(self._current_index)


# Parameter Description
#------------------------------------------------------------------------------
class GetParamDescription(ResponderTest):
  """Check that GET parameter description works for any manufacturer params."""
  CATEGORY = TestCategory.RDM_INFORMATION
  PID = 'PARAMETER_DESCRIPTION'
  REQUIRES = ['manufacturer_parameters']

  def Test(self):
    self.params = self.Property('manufacturer_parameters')[:]
    if len(self.params) == 0:
      self.SetNotRun(' No manufacturer params found')
      self.Stop()
      return
    self._GetParam()

  def _GetParam(self):
    if len(self.params) == 0:
      self.Stop()
      return

    self.AddExpectedResults(
      self.AckResponse(action=self._GetParam))
    self.current_param = self.params.pop()
    self.SendGet(ROOT_DEVICE, self.pid, [self.current_param])

  def VerifyResult(self, status, fields):
    #TODO(simon): Hook into this to add new PIDs to the store
    if not status.WasSuccessfull():
      return

    if self.current_param != fields['pid']:
      self.SetFailed('Request for pid 0x%hx returned pid 0x%hx' %
                     (self.current_param, fields['pid']))

    if fields['type'] != 0:
      self.AddWarning('type field in parameter description is not 0, was %d' %
                      fields['type'])

    if fields['command_class'] > 3:
      self.AddWarning(
          'command class field in parameter description should be 1, 2 or 3, '
          'was %d' % fields['command_class'])
    self._logger.debug(fields)


class GetParamDescriptionForNonManufacturerPid(ResponderTest):
  """GET parameter description for a non-manufacturer pid."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'PARAMETER_DESCRIPTION'
  REQUIRES = ['manufacturer_parameters']

  def Test(self):
    device_info_pid = self.LookupPid('DEVICE_INFO')
    results = [
        self.NackResponse(RDMNack.NR_UNKNOWN_PID),
        self.NackResponse(
            RDMNack.NR_DATA_OUT_OF_RANGE,
            advisory='Parameter Description appears to be supported but no'
                     'manufacturer pids were declared'),
    ]
    if self.Property('manufacturer_parameters'):
      results = self.NackResponse(RDMNack.NR_DATA_OUT_OF_RANGE)

    self.AddExpectedResults(results)
    self.SendGet(ROOT_DEVICE, self.pid, [device_info_pid.value])


class GetParamDescriptionWithData(ResponderTest):
  """GET parameter description with param data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'PARAMETER_DESCRIPTION'
  REQUIRES = ['manufacturer_parameters']

  def Test(self):
    results = [
        self.NackResponse(RDMNack.NR_UNKNOWN_PID),
        self.NackResponse(RDMNack.NR_FORMAT_ERROR,
                          advisory='Parameter Description appears to be '
                                   'supported but no manufacturer pids were '
                                   'declared'),
    ]
    if self.Property('manufacturer_parameters'):
      results = self.NackResponse(RDMNack.NR_FORMAT_ERROR)
    self.AddExpectedResults(results)
    self.SendRawGet(ROOT_DEVICE, self.pid, 'foo')


# Comms Stqtus
#------------------------------------------------------------------------------
class GetCommsStatus(SupportedParamResponderTest):
  """Get the comms status."""
  CATEGORY = TestCategory.STATUS_COLLECTION
  PID = 'COMMS_STATUS'

  def Test(self):
    self.AddIfSupported(self.AckResponse())
    self.SendGet(ROOT_DEVICE, self.pid)


class GetCommsStatusWithData(TestMixins.GetWithDataMixin,
                             SupportedParamResponderTest):
  """Get the comms status with extra data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'COMMS_STATUS'


class ClearCommsStatus(SupportedParamResponderTest):
  """Clear the comms status."""
  CATEGORY = TestCategory.STATUS_COLLECTION
  PID = 'COMMS_STATUS'

  def Test(self):
    self.AddIfSupported(self.AckResponse(action=self.VerifySet))
    self.SendSet(ROOT_DEVICE, self.pid)

  def VerifySet(self):
    self.AddIfSupported(
        self.AckResponse(field_dict={
            'short_message': 0,
            'length_mismatch': 0,
            'checksum_fail': 0
        }))
    self.SendGet(ROOT_DEVICE, self.pid)


class ClearCommsStatusWithData(TestMixins.SetWithDataMixin,
                               SupportedParamResponderTest):
  """Clear the comms status with data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'COMMS_STATUS'


# Product Detail Id List
#------------------------------------------------------------------------------
class GetProductDetailIdList(SupportedParamResponderTest):
  """GET the list of product detail ids."""
  CATEGORY = TestCategory.PRODUCT_INFORMATION
  PID = 'PRODUCT_DETAIL_ID_LIST'

  def Test(self):
    self.AddIfSupported(self.AckResponse(['detail_ids']))
    self.SendGet(ROOT_DEVICE, self.pid)


class GetProductDetailIdListWithData(TestMixins.GetWithDataMixin,
                                     SupportedParamResponderTest):
  """GET product detail id list with param data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'PRODUCT_DETAIL_ID_LIST'


class SetProductDetailIdList(TestMixins.UnsupportedSetMixin,
                             SupportedParamResponderTest):
  """SET product detail id list."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'PRODUCT_DETAIL_ID_LIST'


# Device Model Description
#------------------------------------------------------------------------------
class GetDeviceModelDescription(TestMixins.GetMixin,
                                SupportedParamResponderTest):
  """GET the device model description."""
  CATEGORY = TestCategory.PRODUCT_INFORMATION
  PID = 'DEVICE_MODEL_DESCRIPTION'
  EXPECTED_FIELD = 'description'


class GetDeviceModelDescriptionWithData(TestMixins.GetWithDataMixin,
                                        SupportedParamResponderTest):
  """Get device model description with param data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'DEVICE_MODEL_DESCRIPTION'


class SetDeviceModelDescription(TestMixins.UnsupportedSetMixin,
                                SupportedParamResponderTest):
  """Attempt to SET the device model description with no data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'DEVICE_MODEL_DESCRIPTION'


class SetDeviceModelDescriptionWithData(TestMixins.UnsupportedSetMixin,
                                        SupportedParamResponderTest):
  """SET the device model description with data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'DEVICE_MODEL_DESCRIPTION'
  DATA = 'FOO BAR'


# Manufacturer Label
#------------------------------------------------------------------------------
class GetManufacturerLabel(TestMixins.GetMixin,
                           SupportedParamResponderTest):
  """GET the manufacturer label."""
  CATEGORY = TestCategory.PRODUCT_INFORMATION
  PID = 'MANUFACTURER_LABEL'
  EXPECTED_FIELD = 'label'


class GetManufacturerLabelWithData(TestMixins.GetWithDataMixin,
                                   SupportedParamResponderTest):
  """Get manufacturer label with param data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'MANUFACTURER_LABEL'


class SetManufacturerLabel(TestMixins.UnsupportedSetMixin,
                           SupportedParamResponderTest):
  """Attempt to SET the manufacturer label with no data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'MANUFACTURER_LABEL'


class SetManufacturerLabelWithData(TestMixins.UnsupportedSetMixin,
                                   SupportedParamResponderTest):
  """SET the manufacturer label with data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'MANUFACTURER_LABEL'
  DATA = 'FOO BAR'


# Device Label
#------------------------------------------------------------------------------
class GetDeviceLabel(TestMixins.GetMixin,
                     SupportedParamResponderTest):
  """GET the device label."""
  CATEGORY = TestCategory.PRODUCT_INFORMATION
  PID = 'DEVICE_LABEL'
  PROVIDES = ['device_label']
  EXPECTED_FIELD = 'label'


class GetDeviceLabelWithData(TestMixins.GetWithDataMixin,
                             SupportedParamResponderTest):
  """GET the device label with param data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'DEVICE_LABEL'


class SetDeviceLabel(TestMixins.SetLabelMixin,
                     SupportedParamResponderTest):
  """SET the device label."""
  CATEGORY = TestCategory.PRODUCT_INFORMATION
  PID = 'DEVICE_LABEL'
  REQUIRES = ['device_label']

  def OldValue(self):
    self.Property('device_label')


class SetFullSizeDeviceLabel(TestMixins.SetLabelMixin,
                             SupportedParamResponderTest):
  """SET the device label."""
  CATEGORY = TestCategory.PRODUCT_INFORMATION
  PID = 'DEVICE_LABEL'
  REQUIRES = ['device_label']
  TEST_LABEL = 'this is a string with 32 charact'

  def OldValue(self):
    self.Property('device_label')


class SetNonAsciiDeviceLabel(TestMixins.SetLabelMixin,
                             SupportedParamResponderTest):
  """SET the device label to something that contains non-ascii data."""
  CATEGORY = TestCategory.PRODUCT_INFORMATION
  PID = 'DEVICE_LABEL'
  REQUIRES = ['device_label']
  TEST_LABEL = 'string with\x0d non ascii\xc0'

  def ExpectedResults(self):
    return [
      self.NackResponse(RDMNack.NR_UNSUPPORTED_COMMAND_CLASS),
      self.NackResponse(RDMNack.NR_FORMAT_ERROR),
      self.AckResponse(action=self.VerifySet)
    ]

  def OldValue(self):
    self.Property('device_label')


class SetEmptyDeviceLabel(TestMixins.SetLabelMixin,
                          SupportedParamResponderTest):
  """SET the device label with no data."""
  CATEGORY = TestCategory.PRODUCT_INFORMATION
  PID = 'DEVICE_LABEL'
  REQUIRES = ['device_label']
  TEST_LABEL = ''

  def OldValue(self):
    self.Property('device_label')


class SetOversizedDeviceLabel(TestMixins.SetOversizedLabelMixin,
                              SupportedParamResponderTest):
  """SET the device label with more than 32 bytes of data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  REQUIRES = ['device_label']
  PID = 'DEVICE_LABEL'

  def OldValue(self):
    self.Property('device_label')


# Factory Defaults
#------------------------------------------------------------------------------
class GetFactoryDefaults(SupportedParamResponderTest):
  """GET the factory defaults pid."""
  CATEGORY = TestCategory.PRODUCT_INFORMATION
  PID = 'FACTORY_DEFAULTS'

  def Test(self):
    self.AddIfSupported(self.AckResponse(['using_defaults']))
    self.SendGet(ROOT_DEVICE, self.pid)


class GetFactoryDefaultsWithData(TestMixins.GetWithDataMixin,
                                 SupportedParamResponderTest):
  """GET the factory defaults pid with extra data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'FACTORY_DEFAULTS'


class ResetFactoryDefaults(SupportedParamResponderTest):
  """Reset to factory defaults."""
  CATEGORY = TestCategory.PRODUCT_INFORMATION
  PID = 'FACTORY_DEFAULTS'

  def Test(self):
    self.AddIfSupported(
      self.AckResponse(action=self.VerifySet))
    self.SendSet(ROOT_DEVICE, self.pid)

  def VerifySet(self):
    self.AddIfSupported(
      self.AckResponse(field_values={'using_defaults': True}))
    self.SendGet(ROOT_DEVICE, self.pid)


class ResetFactoryDefaultsWithData(TestMixins.SetWithDataMixin,
                                   SupportedParamResponderTest):
  """Reset to factory defaults with extra data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'FACTORY_DEFAULTS'


# Language Capabilities
#------------------------------------------------------------------------------
class GetLanguageCapabilities(SupportedParamResponderTest):
  """GET the language capabilities pid."""
  CATEGORY = TestCategory.PRODUCT_INFORMATION
  PID = 'LANGUAGE_CAPABILITIES'
  PROVIDES = ['languages_capabilities']

  def Test(self):
    self.languages = []
    self.AddIfSupported(self.AckResponse(['languages']))
    self.SendGet(ROOT_DEVICE, self.pid)

  def VerifyResult(self, status, fields):
    if not status.WasSuccessfull():
      self.SetProperty('languages_capabilities', [])
      return

    self.languages = [f['language'] for f in fields['languages']]

    if len(self.languages) == 0:
      self.AddWarning('No languages returned for LANGUAGE_CAPABILITIES')

    language_set = set()
    for language in self.languages:
      if language in language_set:
        self.AddAdvisory('%s listed twice in language capabilities' % language)
      language_set.add(language)

    self.SetProperty('languages_capabilities', language_set)


class GetLanguageCapabilitiesWithData(TestMixins.GetWithDataMixin,
                                      SupportedParamResponderTest):
  """GET the language capabilities pid with extra data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'LANGUAGE_CAPABILITIES'


# Language
#------------------------------------------------------------------------------
class GetLanguage(TestMixins.GetMixin, SupportedParamResponderTest):
  """GET the language."""
  CATEGORY = TestCategory.PRODUCT_INFORMATION
  PID = 'LANGUAGE'
  PROVIDES = ['language']
  EXPECTED_FIELD = ['language']


class SetLanguage(SupportedParamResponderTest):
  """SET the language."""
  CATEGORY = TestCategory.PRODUCT_INFORMATION
  PID = 'LANGUAGE'
  REQUIRES = ['language', 'languages_capabilities']

  def Test(self):
    ack = self.AckResponse(action=self.VerifySet)
    nack = self.NackResponse(RDMNack.NR_UNSUPPORTED_COMMAND_CLASS)

    available_langugages = self.Property('languages_capabilities')
    if available_langugages:
      if len(available_langugages) > 1:
        # if the responder only supports 1 lang, we may not be able to set it
        self.AddIfSupported(ack)
        self.new_language = available_langugages[0]
        if self.new_language == self.Property('language'):
          self.new_language = available_langugages[2]
      else:
        self.new_language = available_langugages[0]
        self.AddIfSupported([ack, nack])
    else:
      # Get languages returned no languages so we expect a nack
      self.AddIfSupported(nack)
      self.new_language = 'en'

    self.SendSet(ROOT_DEVICE, self.pid, [self.new_language])

  def VerifySet(self):
    self.AddExpectedResults(
      self.AckResponse(field_values={'language': self.new_language}))
    self.SendGet(ROOT_DEVICE, self.pid)


class SetNonAsciiLanguage(SupportedParamResponderTest):
  CATEGORY = TestCategory.PRODUCT_INFORMATION
  PID = 'LANGUAGE'

  def Test(self):
    self.AddIfSupported(self.NackResponse(RDMNack.NR_DATA_OUT_OF_RANGE))

    self.SendSet(ROOT_DEVICE, self.pid, ['\x0d\xc0'])


class SetUnsupportedLanguage(SupportedParamResponderTest):
  """Try to set a language that doesn't exist in Language Capabilities."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'LANGUAGE'
  REQUIRES = ['languages_capabilities']

  def Test(self):
    if 'zz' in self.Property('languages_capabilities'):
      self.SetBroken('zz exists in the list of available languages')
      self.Stop()
      return

    self.AddIfSupported([
      self.NackResponse(RDMNack.NR_UNSUPPORTED_COMMAND_CLASS),
      self.NackResponse(RDMNack.NR_DATA_OUT_OF_RANGE),
    ])
    self.SendSet(ROOT_DEVICE, self.pid, ['zz'])


# Software Version Label
#------------------------------------------------------------------------------
class GetSoftwareVersionLabel(TestMixins.GetRequiredMixin, ResponderTest):
  """GET the software version label."""
  CATEGORY = TestCategory.PRODUCT_INFORMATION
  PID = 'SOFTWARE_VERSION_LABEL'
  EXPECTED_FIELD = 'label'


class GetSoftwareVersionLabelWithData(TestMixins.GetWithDataMixin, ResponderTest):
  """GET the software_version_label with param data."""
  # We don't use the GetLabelMixin here because this PID is mandatory
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'SOFTWARE_VERSION_LABEL'

  def AddIfSupported(self, results):
    self.AddExpectedResults(results)


class SetSoftwareVersionLabel(TestMixins.UnsupportedSetMixin, ResponderTest):
  """Attempt to SET the software version label."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'SOFTWARE_VERSION_LABEL'


# TODO(simon): Add a test for every sub device


# Boot Software Version
#------------------------------------------------------------------------------
class GetBootSoftwareVersion(SupportedParamResponderTest):
  """GET the boot software version."""
  CATEGORY = TestCategory.PRODUCT_INFORMATION
  PID = 'BOOT_SOFTWARE_VERSION'

  def Test(self):
    self.AddIfSupported(self.AckResponse(['version']))
    self.SendGet(ROOT_DEVICE, self.pid)


class GetBootSoftwareVersionWithData(TestMixins.GetWithDataMixin,
                                     SupportedParamResponderTest):
  """GET the boot software version with extra data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'BOOT_SOFTWARE_VERSION'


class SetBootSoftwareVersion(TestMixins.UnsupportedSetMixin, ResponderTest):
  """Attempt to SET the boot software version."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'BOOT_SOFTWARE_VERSION'


# Boot Software Version Label
#------------------------------------------------------------------------------
class GetBootSoftwareLabel(TestMixins.GetMixin,
                           SupportedParamResponderTest):
  """GET the boot software label."""
  CATEGORY = TestCategory.PRODUCT_INFORMATION
  PID = 'BOOT_SOFTWARE_LABEL'
  EXPECTED_FIELD = 'label'


class GetBootSoftwareLabelWithData(TestMixins.GetWithDataMixin,
                                   SupportedParamResponderTest):
  """GET the boot software label with param data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'BOOT_SOFTWARE_LABEL'

class SetBootSoftwareLabel(TestMixins.UnsupportedSetMixin,
                           SupportedParamResponderTest):
  """SET the boot software label."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'BOOT_SOFTWARE_LABEL'


# DMX Personality
#------------------------------------------------------------------------------
class GetZeroPersonalityDescription(SupportedParamResponderTest):
  """GET the personality description for the 0th personality."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'DMX_PERSONALITY_DESCRIPTION'

  def Test(self):
    self.AddIfSupported(self.NackResponse(RDMNack.NR_DATA_OUT_OF_RANGE))
    self.SendGet(ROOT_DEVICE, self.pid, [0])


class GetOutOfRangePersonalityDescription(SupportedParamResponderTest):
  """GET the personality description for the N + 1 personality."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'DMX_PERSONALITY_DESCRIPTION'
  REQUIRES = ['personality_count']

  def Test(self):
    self.AddIfSupported(self.NackResponse(RDMNack.NR_DATA_OUT_OF_RANGE))
    personality_count = self.Property('personality_count')
    self.SendGet(ROOT_DEVICE, self.pid, [personality_count + 1])


class GetPersonalityDescription(SupportedParamResponderTest):
  """GET the personality description for the current personality."""
  CATEGORY = TestCategory.DMX_SETUP
  PID = 'DMX_PERSONALITY_DESCRIPTION'
  REQUIRES = ['current_personality', 'dmx_footprint']

  def Test(self):
    current_personality = self.Property('current_personality')
    footprint = self.Property('dmx_footprint')
    # cross check against what we got from device info
    self.AddIfSupported(self.AckResponse(field_values={
        'personality': current_personality,
        'slots_required': footprint,
      }))
    self.SendGet(ROOT_DEVICE, self.pid, [current_personality])


class GetPersonality(SupportedParamResponderTest):
  """Get the current personality settings."""
  CATEGORY = TestCategory.DMX_SETUP
  PID = 'DMX_PERSONALITY'
  REQUIRES = ['current_personality', 'personality_count']

  def Test(self):
    self.AddIfSupported(self.AckResponse(
      ['current_personality', 'personality_count']))
    self.SendGet(ROOT_DEVICE, self.pid)

  def VerifyResult(self, status, fields):
    if not status.WasSuccessfull():
      return

    current_personality = self.Property('current_personality')
    personality_count = self.Property('personality_count')
    warning_str = ("Personality information in device info doesn't match"
      ' that in dmx_personality')

    if current_personality != fields['current_personality']:
      self.SetFailed('%s: current_personality %d != %d' % (
        warning_str, current_personality, fields['current_personality']))

    if personality_count != fields['personality_count']:
      self.SetFailed('%s: personality_count %d != %d' % (
        warning_str, personality_count, fields['personality_count']))


class GetPersonalities(SupportedParamResponderTest):
  """Get information about all the personalities."""
  CATEGORY = TestCategory.DMX_SETUP
  PID = 'DMX_PERSONALITY_DESCRIPTION'
  REQUIRES = ['personality_count']
  PROVIDES = ['personalities']

  def Test(self):
    self._personalities = []
    self._personality_count = self.Property('personality_count')
    self._current_index = 0
    self._GetPersonality()

  def _GetPersonality(self):
    self._current_index += 1
    if self._current_index > self._personality_count:
      if self._personality_count == 0:
        self.SetNotRun(' No personalities declared')
      self.SetProperty('personalities', self._personalities)
      self.Stop()
      return

    if self._current_index >= MAX_PERSONALITY_NUMBER:
      # This should never happen because personality_count is a uint8
      self.SetFailed('Could not find all personalities')
      self.Stop()
      return

    self.AddIfSupported(self.AckResponse(
        ['slots_required', 'name'],
        {'personality': self._current_index},
        action=self._GetPersonality))
    self.SendGet(ROOT_DEVICE, self.pid, [self._current_index])

  def VerifyResult(self, status, fields):
    """Save the personality for other tests to use."""
    if status.WasSuccessfull():
      self._personalities.append(fields)


class SetPersonality(SupportedParamResponderTest):
  """Set the personality."""
  CATEGORY = TestCategory.DMX_SETUP
  PID = 'DMX_PERSONALITY'
  # This ensures we don't modify the current personality before GetPersonality
  # and GetPersonalityDescription run
  DEPS = [GetPersonality, GetPersonalityDescription]
  REQUIRES = ['current_personality', 'personality_count', 'personalities']

  def Test(self):
    count = self.Property('personality_count')
    if count is None or count == 0:
      self.AddExpectedResults(self.NackResponse(RDMNack.NR_UNKNOWN_PID))
      self.new_personality = {'personality': 1}  # can use anything here really
    else:
      personalities = self.Property('personalities')
      current = self.Property('current_personality')

      if len(personalities) == 0:
        self.SetFailed(
          'personality_count was non 0 but failed to fetch all personalities')
        self.Stop()
        return

      self.new_personality = personalities[0]
      for personality in personalities:
        if personality['personality'] != current:
          self.new_personality = personality
          break

      self.AddIfSupported(self.AckResponse(action=self.VerifySet))

    self.SendSet(ROOT_DEVICE,
                 self.pid,
                 [self.new_personality['personality']])

  def VerifySet(self):
    self.AddIfSupported(
      self.AckResponse(
        field_values={
          'current_personality': self.new_personality['personality'],
        },
        action=self.VerifyDeviceInfo))
    self.SendGet(ROOT_DEVICE, self.pid)

  def VerifyDeviceInfo(self):
    device_info_pid = self.LookupPid('DEVICE_INFO')
    self.AddIfSupported(
      ExpectedResult.AckResponse(
        device_info_pid.value,
        field_values={
          'current_personality': self.new_personality['personality'],
          'dmx_footprint': self.new_personality['slots_required'],
        }))
    self.SendGet(ROOT_DEVICE, device_info_pid)


class SetZeroPersonality(SupportedParamResponderTest):
  """Try to set the personality to 0."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'DMX_PERSONALITY'

  def Test(self):
    self.AddIfSupported(self.NackResponse(RDMNack.NR_DATA_OUT_OF_RANGE))
    self.SendSet(ROOT_DEVICE, self.pid, [0])


class SetOutOfRangePersonality(SupportedParamResponderTest):
  """Try to set the personality to 0."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'DMX_PERSONALITY'
  REQUIRES = ['personality_count']

  def Test(self):
    personality_count = self.Property('personality_count')
    self.AddIfSupported(self.NackResponse(RDMNack.NR_DATA_OUT_OF_RANGE))
    self.SendSet(ROOT_DEVICE, self.pid, [personality_count + 1])


class SetOversizedPersonality(SupportedParamResponderTest):
  """Send an over-sized SET personality command."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'DMX_PERSONALITY'

  def Test(self):
    self.AddIfSupported(self.NackResponse(RDMNack.NR_FORMAT_ERROR))
    self.SendRawSet(ROOT_DEVICE, self.pid, 'foo')


# DMX Start Address tests
#------------------------------------------------------------------------------
class GetStartAddress(ResponderTest):
  """GET the DMX start address."""
  CATEGORY = TestCategory.DMX_SETUP
  PID = 'DMX_START_ADDRESS'
  REQUIRES = ['dmx_footprint', 'dmx_start_address']
  PROVIDES = ['dmx_address']

  def Test(self):
    if self.Property('dmx_footprint') > 0:
      results = self.AckResponse(['dmx_address'])
    else:
      results = [
          self.AckResponse(field_values={'dmx_address': 0xffff}),
          self.NackResponse(RDMNack.NR_UNKNOWN_PID)
      ]
    self.AddExpectedResults(results)
    self.SendGet(ROOT_DEVICE, self.pid)

  def VerifyResult(self, status, fields):
    if not status.WasSuccessfull():
      self.SetPropertyFromDict(fields, None)
      return

    if self.Property('dmx_start_address') != fields['dmx_address']:
      self.SetFailed(
          'DMX_START_ADDRESS (%d) doesn\'t match what was in DEVICE_INFO (%d)'
          % (self.Property('dmx_start_address'), fields['dmx_address']))
    self.SetPropertyFromDict(fields, 'dmx_address')


class SetStartAddress(ResponderTest):
  """Set the DMX start address."""
  CATEGORY = TestCategory.DMX_SETUP
  PID = 'DMX_START_ADDRESS'
  REQUIRES = ['dmx_footprint', 'dmx_address']

  def Test(self):
    footprint = self.Property('dmx_footprint')
    self.start_address = 1

    current_address = self.Property('dmx_address')
    if footprint == 0 or current_address == 0xffff:
      result = self.NackResponse(RDMNack.NR_UNKNOWN_PID)
    else:
      if footprint != MAX_DMX_ADDRESS:
        self.start_address = current_address + 1
        if self.start_address + footprint > MAX_DMX_ADDRESS + 1:
          self.start_address = 1
      result = self.AckResponse(action=self.VerifySet)
    self.AddExpectedResults(result)
    self.SendSet(ROOT_DEVICE, self.pid, [self.start_address])

  def VerifySet(self):
    self.AddExpectedResults(
      self.AckResponse(field_values={'dmx_address': self.start_address},
                       action=self.VerifyDeviceInfo))
    self.SendGet(ROOT_DEVICE, self.pid)

  def VerifyDeviceInfo(self):
    device_info_pid = self.LookupPid('DEVICE_INFO')
    self.AddExpectedResults(
      ExpectedResult.AckResponse(
        device_info_pid.value,
        field_values = {'dmx_start_address': self.start_address}))
    self.SendGet(ROOT_DEVICE, device_info_pid)


class SetOutOfRangeStartAddress(ResponderTest):
  """Check that the DMX address can't be set to > 512."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'DMX_START_ADDRESS'
  # we depend on dmx_address to make sure this runs in GetStartAddress
  DEPS = [GetStartAddress]
  REQUIRES = ['dmx_footprint']

  def Test(self):
    if self.Property('dmx_footprint') > 0:
      self.AddExpectedResults(self.NackResponse(RDMNack.NR_DATA_OUT_OF_RANGE))
    else:
      self.AddExpectedResults(self.NackResponse(RDMNack.NR_UNKNOWN_PID))
    data = struct.pack('!H', MAX_DMX_ADDRESS + 1)
    self.SendRawSet(ROOT_DEVICE, self.pid, data)


class SetZeroStartAddress(ResponderTest):
  """Check the DMX address can't be set to 0."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'DMX_START_ADDRESS'
  # we depend on dmx_address to make sure this runs in GetStartAddress
  DEPS = [GetStartAddress]
  REQUIRES = ['dmx_footprint']

  def Test(self):
    if self.Property('dmx_footprint') > 0:
      self.AddExpectedResults(self.NackResponse(RDMNack.NR_DATA_OUT_OF_RANGE))
    else:
      self.AddExpectedResults(self.NackResponse(RDMNack.NR_UNKNOWN_PID))
    data = struct.pack('!H', 0)
    self.SendRawSet(ROOT_DEVICE, self.pid, data)


class SetOversizedStartAddress(ResponderTest):
  """Send an over-sized SET dmx start address."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'DMX_START_ADDRESS'
  # we depend on dmx_address to make sure this runs in GetStartAddress
  DEPS = [GetStartAddress]
  REQUIRES = ['dmx_footprint']

  def Test(self):
    if self.Property('dmx_footprint') > 0:
      self.AddExpectedResults(self.NackResponse(RDMNack.NR_FORMAT_ERROR))
    else:
      self.AddExpectedResults(self.NackResponse(RDMNack.NR_UNKNOWN_PID))
    self.SendRawSet(ROOT_DEVICE, self.pid, 'foo')


# Device Hours
#------------------------------------------------------------------------------
class GetDeviceHours(TestMixins.GetMixin, SupportedParamResponderTest):
  """GET the device hours."""
  CATEGORY = TestCategory.POWER_LAMP_SETTINGS
  PID = 'DEVICE_HOURS'
  EXPECTED_FIELD = 'hours'
  PROVIDES = ['device_hours']


class GetDeviceHoursWithData(TestMixins.GetWithDataMixin,
                             SupportedParamResponderTest):
  """GET the device hours with extra data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'DEVICE_HOURS'


class SetDeviceHours(TestMixins.SetUInt32Mixin,
                     SupportedParamResponderTest):
  """Attempt to SET the device hours."""
  CATEGORY = TestCategory.POWER_LAMP_SETTINGS
  PID = 'DEVICE_HOURS'
  EXPECTED_FIELD = 'hours'
  REQUIRES = ['device_hours']

  def OldValue(self):
    return self.Property('device_hours')


class SetDeviceHoursWithNoData(TestMixins.SetWithNoDataMixin,
                               SupportedParamResponderTest):
  """Set the device hours with no param data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'DEVICE_HOURS'


# Lamp Hours
#------------------------------------------------------------------------------
class GetLampHours(TestMixins.GetMixin, SupportedParamResponderTest):
  """GET the device hours."""
  CATEGORY = TestCategory.POWER_LAMP_SETTINGS
  PID = 'LAMP_HOURS'
  EXPECTED_FIELD = 'hours'
  PROVIDES = ['lamp_hours']


class GetLampHoursWithData(TestMixins.GetWithDataMixin,
                           SupportedParamResponderTest):
  """GET the device hours with extra data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'LAMP_HOURS'


class SetLampHours(TestMixins.SetUInt32Mixin,
                   SupportedParamResponderTest):
  """Attempt to SET the device hours."""
  CATEGORY = TestCategory.POWER_LAMP_SETTINGS
  PID = 'LAMP_HOURS'
  EXPECTED_FIELD = 'hours'
  REQUIRES = ['lamp_hours']

  def OldValue(self):
    return self.Property('lamp_hours')


class SetLampHoursWithNoData(TestMixins.SetWithNoDataMixin,
                             SupportedParamResponderTest):
  """Set the device hours with no param data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'LAMP_HOURS'


# Lamp Strikes
#------------------------------------------------------------------------------
class GetLampStrikes(TestMixins.GetMixin, SupportedParamResponderTest):
  """GET the device strikes."""
  CATEGORY = TestCategory.POWER_LAMP_SETTINGS
  PID = 'LAMP_STRIKES'
  EXPECTED_FIELD = 'strikes'
  PROVIDES = ['lamp_strikes']


class GetLampStrikesWithData(TestMixins.GetWithDataMixin,
                             SupportedParamResponderTest):
  """GET the device strikes with extra data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'LAMP_STRIKES'


class SetLampStrikes(TestMixins.SetUInt32Mixin, SupportedParamResponderTest):
  """Attempt to SET the device strikes."""
  CATEGORY = TestCategory.POWER_LAMP_SETTINGS
  PID = 'LAMP_STRIKES'
  EXPECTED_FIELD = 'strikes'
  REQUIRES = ['lamp_strikes']

  def OldValue(self):
    return self.Property('lamp_strikes')


class SetLampStrikesWithNoData(TestMixins.SetWithNoDataMixin,
                               SupportedParamResponderTest):
  """Set the device strikes with no param data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'LAMP_STRIKES'


# Device Hours
#------------------------------------------------------------------------------
class GetDevicePowerCycles(TestMixins.GetMixin, SupportedParamResponderTest):
  """GET the device power_cycles."""
  CATEGORY = TestCategory.POWER_LAMP_SETTINGS
  PID = 'DEVICE_POWER_CYCLES'
  EXPECTED_FIELD = 'power_cycles'
  PROVIDES = ['power_cycles']


class GetDevicePowerCyclesWithData(TestMixins.GetWithDataMixin,
                                   SupportedParamResponderTest):
  """GET the device power_cycles with extra data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'DEVICE_POWER_CYCLES'


class SetDevicePowerCycles(TestMixins.SetUInt32Mixin,
                           SupportedParamResponderTest):
  """Attempt to SET the device power_cycles."""
  CATEGORY = TestCategory.POWER_LAMP_SETTINGS
  PID = 'DEVICE_POWER_CYCLES'
  EXPECTED_FIELD = 'power_cycles'
  REQUIRES = ['power_cycles']

  def OldValue(self):
    return self.Property('power_cycles')


class SetDevicePowerCyclesWithNoData(TestMixins.SetWithNoDataMixin,
                                     SupportedParamResponderTest):
  """Set the device power_cycles with no param data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'DEVICE_POWER_CYCLES'


# Display Level
#------------------------------------------------------------------------------
class GetDisplayLevel(TestMixins.GetMixin,
                      SupportedParamResponderTest):
  """GET the display level setting."""
  CATEGORY = TestCategory.DISPLAY_SETTINGS
  PID = 'DISPLAY_LEVEL'
  EXPECTED_FIELD = 'level'
  PROVIDES = ['display_level']


class GetDisplayLevelWithData(TestMixins.GetWithDataMixin,
                              SupportedParamResponderTest):
  """GET the pan invert setting with extra data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'DISPLAY_LEVEL'


class SetDisplayLevel(TestMixins.SetUInt8Mixin,
                      SupportedParamResponderTest):
  """Attempt to SET the display level setting."""
  CATEGORY = TestCategory.DISPLAY_SETTINGS
  PID = 'DISPLAY_LEVEL'
  EXPECTED_FIELD = 'level'
  REQUIRES = ['display_level']

  def OldValue(self):
    return self.Property('display_level')


class SetDisplayLevelWithNoData(TestMixins.SetWithNoDataMixin,
                                SupportedParamResponderTest):
  """Set the display level with no param data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'DISPLAY_LEVEL'


# Pan Invert
#------------------------------------------------------------------------------
class GetPanInvert(TestMixins.GetMixin, SupportedParamResponderTest):
  """GET the pan invert setting."""
  CATEGORY = TestCategory.CONFIGURATION
  PID = 'PAN_INVERT'
  EXPECTED_FIELD = 'invert'
  PROVIDES = ['pan_invert']


class GetPanInvertWithData(TestMixins.GetWithDataMixin,
                           SupportedParamResponderTest):
  """GET the pan invert setting with extra data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'PAN_INVERT'


class SetPanInvert(TestMixins.SetBoolMixin, SupportedParamResponderTest):
  """Attempt to SET the pan invert setting."""
  CATEGORY = TestCategory.CONFIGURATION
  PID = 'PAN_INVERT'
  EXPECTED_FIELD = 'invert'
  REQUIRES = ['pan_invert']

  def OldValue(self):
    return self.Property('pan_invert')


class SetPanInvertWithNoData(TestMixins.SetWithNoDataMixin,
                             SupportedParamResponderTest):
  """Set the pan invert with no param data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'PAN_INVERT'


# Tilt Invert
#------------------------------------------------------------------------------
class GetTiltInvert(TestMixins.GetMixin, SupportedParamResponderTest):
  """GET the tilt invert setting."""
  CATEGORY = TestCategory.CONFIGURATION
  PID = 'TILT_INVERT'
  EXPECTED_FIELD = 'invert'
  PROVIDES = ['tilt_invert']


class GetTiltInvertWithData(TestMixins.GetWithDataMixin,
                            SupportedParamResponderTest):
  """GET the tilt invert setting with extra data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'TILT_INVERT'


class SetTiltInvert(TestMixins.SetBoolMixin, SupportedParamResponderTest):
  """Attempt to SET the tilt invert setting."""
  CATEGORY = TestCategory.CONFIGURATION
  PID = 'TILT_INVERT'
  EXPECTED_FIELD = 'invert'
  REQUIRES = ['tilt_invert']

  def OldValue(self):
    return self.Property('tilt_invert')


class SetTiltInvertWithNoData(TestMixins.SetWithNoDataMixin,
                              SupportedParamResponderTest):
  """Set the tilt invert with no param data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'TILT_INVERT'


# Pan Tilt Swap Invert
#------------------------------------------------------------------------------
class GetPanTiltSwap(TestMixins.GetMixin, SupportedParamResponderTest):
  """GET the pan tilt swap setting."""
  CATEGORY = TestCategory.CONFIGURATION
  PID = 'PAN_TILT_SWAP'
  EXPECTED_FIELD = 'swap'
  PROVIDES = ['pan_tilt_swap']


class GetPanTiltSwapWithData(TestMixins.GetWithDataMixin,
                             SupportedParamResponderTest):
  """GET the pan tilt swap setting with extra data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'PAN_TILT_SWAP'


class SetPanTiltSwap(TestMixins.SetBoolMixin, SupportedParamResponderTest):
  """Attempt to SET the pan tilt swap setting."""
  CATEGORY = TestCategory.CONFIGURATION
  PID = 'PAN_TILT_SWAP'
  EXPECTED_FIELD = 'swap'
  REQUIRES = ['pan_tilt_swap']

  def OldValue(self):
    return self.Property('pan_tilt_swap')


class SetPanTiltSwapWithNoData(TestMixins.SetWithNoDataMixin,
                               SupportedParamResponderTest):
  """Set the pan tilt swap with no param data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'PAN_TILT_SWAP'


# Real time clock
#------------------------------------------------------------------------------
class GetRealTimeClock(SupportedParamResponderTest):
  """GET the real time clock setting."""
  CATEGORY = TestCategory.CONFIGURATION
  PID = 'REAL_TIME_CLOCK'

  ALLOWED_RANGES = {
      'year': (2003, 65535),
      'month': (1, 12),
      'day': (1, 31),
      'hour': (0, 23),
      'minute': (0, 59),
  }

  def Test(self):
    self.AddIfSupported(
      self.AckResponse(self.ALLOWED_RANGES.keys() + ['second']))
    self.SendGet(ROOT_DEVICE, self.pid)

  def VerifyResult(self, status, fields):
    if not status.WasSuccessfull():
      return

    for field, range in ALLOWED_RANGES:
      value = fields[field]
      if value < range[0] or value > range[1]:
        self.AddWarning('%s in GET %s is out of range, was %d, expeced %s' %
                        (field, self.PID, value, range))


class GetRealTimeClockWithData(TestMixins.GetWithDataMixin,
                               SupportedParamResponderTest):
  """GET the teal time clock with data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'REAL_TIME_CLOCK'


class SetRealTimeClock(SupportedParamResponderTest):
  """Set the real time clock."""
  CATEGORY = TestCategory.CONFIGURATION
  PID = 'REAL_TIME_CLOCK'

  def Test(self):
    n = datetime.datetime.now()
    self.AddIfSupported(self.AckResponse())
    args = [n.year, n.month, n.day, n.hour, n.minute, n.second]
    self.SendSet(ROOT_DEVICE, self.pid,
                 args)


class SetRealTimeClockWithNoData(TestMixins.SetWithNoDataMixin,
                                 SupportedParamResponderTest):
  """Set the real time clock without any data."""
  CATEGORY = TestCategory.CONFIGURATION
  PID = 'REAL_TIME_CLOCK'


# Identify Device
#------------------------------------------------------------------------------
class GetIdentifyDevice(TestMixins.GetRequiredMixin, ResponderTest):
  """Get the identify mode."""
  CATEGORY = TestCategory.CONTROL
  PID = 'IDENTIFY_DEVICE'
  PROVIDES = ['identify_state']
  EXPECTED_FIELD = 'identify_state'


class GetIdentifyDeviceWithData(ResponderTest):
  """Get the identify mode with data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'IDENTIFY_DEVICE'

  def Test(self):
    # don't inherit from GetWithDataMixin because this is required
    self.AddExpectedResults(self.NackResponse(RDMNack.NR_FORMAT_ERROR))
    self.SendRawGet(ROOT_DEVICE, self.pid, 'foo')


class SetIdentifyDevice(ResponderTest):
  """Set the identify mode."""
  CATEGORY = TestCategory.CONTROL
  PID = 'IDENTIFY_DEVICE'
  REQUIRES = ['identify_state']

  def Test(self):
    self.identify_mode = self.Property('identify_state')
    self.new_mode = not self.identify_mode

    self.AddExpectedResults(self.AckResponse(action=self.VerifyIdentifyMode))
    self.SendSet(ROOT_DEVICE, self.pid, [self.new_mode])

  def VerifyIdentifyMode(self):
    self.AddExpectedResults(self.AckResponse(
        field_values = {'identify_state': self.new_mode},
        action=self.ResetMode))
    self.SendGet(ROOT_DEVICE, self.pid)

  def ResetMode(self):
    self.AddExpectedResults(self.AckResponse())
    self.SendSet(ROOT_DEVICE, self.pid, [self.identify_mode])


class SetIdentifyDeviceWithNoData(ResponderTest):
  """Set the identify mode with no data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'IDENTIFY_DEVICE'

  def Test(self):
    self.AddExpectedResults(self.NackResponse(RDMNack.NR_FORMAT_ERROR))
    self.SendRawSet(ROOT_DEVICE, self.pid, '')


# Power State
#------------------------------------------------------------------------------
class GetPowerState(TestMixins.GetMixin, SupportedParamResponderTest):
  """Get the power state mode."""
  CATEGORY = TestCategory.CONTROL
  PID = 'POWER_STATE'
  PROVIDES = ['power_state']
  EXPECTED_FIELD = 'power_state'

  # The allowed power states
  ALLOWED_STATES = [0, 1, 2, 0xff]

  def VerifyResult(self, status, fields):
    super(GetPowerState, self).VerifyResult(status, fields)
    if status.WasSuccessfull():
      if fields['power_state'] not in self.ALLOWED_STATES:
        self.AddWarning('Power state of 0x%hx is not defined' %
                        fields['power_state'])


class GetPowerStateWithData(TestMixins.GetWithDataMixin,
                            SupportedParamResponderTest):
  """Get the power state mode with data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'POWER_STATE'


class SetPowerState(TestMixins.SetUInt8Mixin, SupportedParamResponderTest):
  """Set the power state."""
  CATEGORY = TestCategory.CONTROL
  PID = 'POWER_STATE'
  REQUIRES = ['power_state']
  EXPECTED_FIELD = 'power_state'

  def NewValue(self):
    self.old_value = self.Property('power_state')
    try:
      index = GetPowerState.ALLOWED_STATES.index(self.old_value)
    except ValueError:
      return GetPowerState.ALLOWED_STATES[0]

    length = len(GetPowerState.ALLOWED_STATES)
    return GetPowerState.ALLOWED_STATES[(self.old_value + 1) % length]

  def ResetState(self):
    if not self.old_value:
      return

    # reset back to the old value
    self.SendSet(ROOT_DEVICE, self.pid, [self.old_value])
    self._wrapper.Run()


class SetPowerStateWithNoData(TestMixins.SetWithNoDataMixin,
                              SupportedParamResponderTest):
  """Set the power state with no data."""
  CATEGORY = TestCategory.ERROR_CONDITIONS
  PID = 'POWER_STATE'
