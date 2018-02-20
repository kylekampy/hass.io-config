"""
Support for monitoring a Sense energy sensor.

For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/sensor.sense/
"""
import logging
from datetime import timedelta

import voluptuous as vol

from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import (CONF_EMAIL, CONF_PASSWORD, CONF_MONITORED_CONDITIONS)
from homeassistant.helpers.entity import Entity
from homeassistant.util import Throttle
import homeassistant.helpers.config_validation as cv

REQUIREMENTS = ['sense_energy==0.3.0']

_LOGGER = logging.getLogger(__name__)

ACTIVE_NAME = 'Energy'
DAILY_NAME = 'Daily'
WEEKLY_NAME = 'Weekly'
MONTHLY_NAME = 'Monthly'
YEARLY_NAME = 'Yearly'

PRODUCTION_NAME = 'Production'
CONSUMPTION_NAME = 'Usage'

ACTIVE_TYPE = 'active'
DAILY_TYPE = 'DAY'
WEEKLY_TYPE = 'WEEK'
MONTHLY_TYPE = 'MONTH'
YEARLY_TYPE = 'YEAR'

CONSUMPTION_ICON = 'mdi:flash'
PRODUCTION_ICON = 'mdi:white-balance-sunny'

SENSE_MONITORED_CONDITIONS = ['production', 'consumption', 'devices']

MIN_TIME_BETWEEN_DAILY_UPDATES = timedelta(seconds=300)
MIN_TIME_BETWEEN_ACTIVE_UPDATES = timedelta(seconds=60)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_EMAIL): cv.string,
    vol.Required(CONF_PASSWORD): cv.string,
    vol.Required(CONF_MONITORED_CONDITIONS):
        vol.All(cv.ensure_list, vol.Length(min=1), [vol.In(SENSE_MONITORED_CONDITIONS)]),
})


def setup_platform(hass, config, add_devices, discovery_info=None):
    """Set up the Sense sensor."""
    # from sense_energy import Senseable

    username = config.get(CONF_EMAIL)
    password = config.get(CONF_PASSWORD)
    monitored_conditions = config.get(CONF_MONITORED_CONDITIONS)

    data = Senseable(username, password)

    @Throttle(MIN_TIME_BETWEEN_DAILY_UPDATES)
    def update_trends():
        """Update the daily power usage."""
        data.update_trend_data()

    @Throttle(MIN_TIME_BETWEEN_ACTIVE_UPDATES)
    def update_active():
        """Update the active power usage."""
        data.get_realtime()

    dev = []
    for condition in monitored_conditions:
        if condition == 'production':
            dev.extend([
                SenseProductionConsumption(data, ACTIVE_NAME, ACTIVE_TYPE, True, update_active),
                SenseProductionConsumption(data, DAILY_NAME, DAILY_TYPE, True, update_trends),
                SenseProductionConsumption(data, WEEKLY_NAME, WEEKLY_TYPE, True, update_trends),
                SenseProductionConsumption(data, MONTHLY_NAME, MONTHLY_TYPE, True, update_trends),
                SenseProductionConsumption(data, YEARLY_NAME, YEARLY_TYPE, True, update_trends),
            ])
        elif condition == 'consumption':
            dev.extend([
                SenseProductionConsumption(data, ACTIVE_NAME, ACTIVE_TYPE, False, update_active),
                SenseProductionConsumption(data, DAILY_NAME, DAILY_TYPE, False, update_trends),
                SenseProductionConsumption(data, WEEKLY_NAME, WEEKLY_TYPE, False, update_trends),
                SenseProductionConsumption(data, MONTHLY_NAME, MONTHLY_TYPE, False, update_trends),
                SenseProductionConsumption(data, YEARLY_NAME, YEARLY_TYPE, False, update_trends),
            ])
        elif condition == 'devices':
            devices = data.get_discovered_device_data()
            dev.extend(map(lambda d: SenseDevice(data, d['name'], d.get('location', ''), d['icon']), devices))

    add_devices(dev)

class SenseDevice(Entity):
    """Implementation of a Sense detected device."""

    def __init__(self, data, name, location, icon):
        """Initialize the sensor."""
        self._device_name = name
        if location != '':
            self._device_name = '{} ({})'.format(name, location)
        self._name = '{} Energy Usage'.format(self._device_name)
        self._data = data
        self._icon = icon
        self._state = None

    @property
    def name(self):
        """Return the name of the sensor"""
        return self._name

    @property
    def state(self):
        """Return the state of the sensor"""
        return self._state

    @property
    def force_update(self):
        # Because this sensor represents a reading at a moment in time, each update that has
        # an identical value is still a valid reading that we want to track.
        return True

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of this entity"""
        return 'W'

    @property
    def icon(self):
        """Icon to use in the frontend, if any."""
        # A handful of devices from Sense coincidentally provide matching mdi icons
        if (self._icon == 'fridge' or \
            self._icon == 'lightbulb' or \
            self._icon == 'stove' or \
            self._icon == 'fan'):
            return 'mdi:{}'.format(self._icon)
        elif self._icon == 'microwave':
            return 'mdi:waves'
        elif self._icon == 'alwayson':
            return 'mdi:sync'
        elif self._icon == 'home': # the other/unknown
            return 'mdi:help'
        else:
            return CONSUMPTION_ICON

    def update(self):
        """Get the latest data, update state."""
        payload = self._data.get_realtime()
        device_on = False
        if 'devices' in payload:
            for device in payload['devices']:
                if (device['name'] == self._device_name):
                    self._state = round(device['w'])
                    device_on = self._state > 0

        if (device_on == False):
            self._state = 0


class SenseProductionConsumption(Entity):
    """Implementation of a Sense energy sensor."""

    def __init__(self, data, name, sensor_type, is_production, update_call):
        """Initialize the sensor."""
        name_type = PRODUCTION_NAME if is_production else CONSUMPTION_NAME
        self._name = "{} {}".format(name, name_type)
        self._data = data
        self._sensor_type = sensor_type
        self.update_sensor = update_call
        self._is_production = is_production
        self._state = None

        if sensor_type == ACTIVE_TYPE:
            self._unit_of_measurement = 'W'
        else:
            self._unit_of_measurement = 'kWh'

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of this entity, if any."""
        return self._unit_of_measurement

    @property
    def icon(self):
        """Icon to use in the frontend, if any."""
        if self._is_production:
            return PRODUCTION_ICON
        return CONSUMPTION_ICON

    @property
    def force_update(self):
        # Because this sensor represents a reading at a moment in time, each update that has
        # an identical value is still a valid reading that we want to track.
        return True

    def update(self):
        """Get the latest data, update state."""
        self.update_sensor()

        if self._sensor_type == ACTIVE_TYPE:
            if self._is_production:
                self._state = round(self._data.active_solar_power)
            else:
                self._state = round(self._data.active_power)
        else:
            state = self._data.get_trend(self._sensor_type,
                                         self._is_production)
            self._state = round(state, 1)



import json
import requests
from datetime import datetime
from websocket import create_connection

API_URL = 'https://api.sense.com/apiservice/api/v1/'
API_TIMEOUT = 1
WSS_TIMEOUT = 1

# for the last hour, day, week, month, or year
valid_scales = ['HOUR', 'DAY', 'WEEK', 'MONTH', 'YEAR']

class Senseable(object):

    def __init__(self, username, password):
        auth_data = {
            "email": username,
            "password": password
        }

        # Create session
        self.s = requests.session()
        self._realtime = None
        self._devices = []
        self._trend_data = {}
        for scale in valid_scales: self._trend_data[scale] = {}

        # Get auth token
        try:
            response = self.s.post(API_URL+'authenticate', auth_data, timeout=API_TIMEOUT)
        except Exception as e:
            raise Exception('Connection failure: %s' % e)

        # check for 200 return
        if response.status_code != 200:
            raise Exception("Please check username and password. API Return Code: %s" % response.status_code)

        # Build out some common variables
        self.sense_access_token = response.json()['access_token']
        self.sense_user_id = response.json()['user_id']
        self.sense_monitor_id = response.json()['monitors'][0]['id']

        # create the auth header
        self.headers = {'Authorization': 'bearer {}'.format(self.sense_access_token)}

    @property
    def devices(self):
        """Return devices."""
        return self._devices

    def get_realtime(self):
        ws = create_connection("wss://clientrt.sense.com/monitors/%s/realtimefeed?access_token=%s" %
                               (self.sense_monitor_id, self.sense_access_token),
                               timeout=WSS_TIMEOUT)

        # Sense websocket starts off with a few introductory frames before the real data:
        #  1) A simple "hello" with a `type` == 'hello'
        #  2) Monitor features, with a `type` == 'MonitorInfo'
        #  3) Possibly may be a frame with recent timeline data. `type` == 'DataChange'
        #  4+) 'realtime_update' with all the useful data for all active devices
        for i in range(4):
            result = json.loads(ws.recv())
            if 'type' in result and result['type'] == 'realtime_update':
                self._realtime = result['payload']
                return self._realtime

    @property
    def active_power(self):
        if not self._realtime: self.get_realtime()
        return self._realtime.get('w', 0)

    @property
    def active_solar_power(self):
        if not self._realtime: self.get_realtime()
        return self._realtime.get('solar_w', 0)
    
    @property
    def daily_usage(self):
        return self.get_trend('DAY', False)

    @property
    def daily_production(self):
        return self.get_trend('DAY', True)
    
    @property
    def weekly_usage(self):
        # Add today's usage
        return self.get_trend('WEEK', False)

    @property
    def weekly_production(self):
        # Add today's production
        return self.get_trend('WEEK', True)
    
    @property
    def monthly_usage(self):
        # Add today's usage
        return self.get_trend('MONTH', False)

    @property
    def monthly_production(self):
        # Add today's production
        return self.get_trend('MONTH', True)
    
    @property
    def yearly_usage(self):
        # Add this month's usage
        return self.get_trend('YEAR', False)

    @property
    def yeary_production(self):
        # Add this month's production
        return self.get_trend('YEAR', True)

    @property
    def active_devices(self):
        if not self._realtime: self.get_realtime()
        return [d['name'] for d in self._realtime.get('devices', {})]

    def get_trend(self, scale, is_production):
        key = "production" if is_production else "consumption"
        if not self._trend_data[scale]: self.get_trend_data(scale)         
        if key not in self._trend_data[scale]: return 0
        total = self._trend_data[scale][key].get('total', 0)
        if scale == 'WEEK' or scale == 'MONTH':
            return total + self.get_trend('DAY', is_production)
        if scale == 'YEAR':
            return total + self.get_trend('MONTH', is_production)
        return total

    def get_discovered_device_names(self):
        # lots more info in here to be parsed out
        response = self.s.get(API_URL + 'app/monitors/%s/devices' %
                              self.sense_monitor_id,
                              headers=self.headers, timeout=API_TIMEOUT)
        self._devices = [entry['name'] for entry in response.json()]
        return self._devices

    def get_discovered_device_data(self):
        response = self.s.get(API_URL + 'monitors/%s/devices' %
                              self.sense_monitor_id,
                              headers=self.headers, timeout=API_TIMEOUT)
        return response.json()

    def always_on_info(self):
        # Always on info - pretty generic similar to the web page
        response = self.s.get(API_URL + 'app/monitors/%s/devices/always_on' %
                              self.sense_monitor_id,
                              headers=self.headers, timeout=API_TIMEOUT)
        return response.json()

    def get_monitor_info(self):
        # View info on your monitor & device detection status
        response = self.s.get(API_URL + 'app/monitors/%s/status' %
                              self.sense_monitor_id,
                              headers=self.headers, timeout=API_TIMEOUT)
        return response.json()

    def get_device_info(self, device_id):
        # Get specific informaton about a device
        response = self.s.get(API_URL + 'app/monitors/%s/devices/%s' %
                              (self.sense_monitor_id, device_id),
                              headers=self.headers, timeout=API_TIMEOUT)
        return response.json()

    def get_notification_preferences(self):
        # Get notification preferences
        payload = {'monitor_id': '%s' % self.sense_monitor_id}
        response = self.s.get(API_URL + 'users/%s/notifications' %
                              self.sense_user_id,
                              headers=self.headers, timeout=API_TIMEOUT,
                              data=payload)
        return response.json()
    
    def get_trend_data(self, scale):
        if scale.upper() not in valid_scales:
            raise Exception("%s not a valid scale" % scale)
        response = self.s.get(API_URL + 'app/history/trends?monitor_id=%s&scale=%s&start=%s' %
                              (self.sense_monitor_id, scale, datetime.now().isoformat()),
                              headers=self.headers, timeout=API_TIMEOUT)
        self._trend_data[scale] = response.json()

    def update_trend_data(self):
        for scale in valid_scales:
            self.get_trend_data(scale)

    def get_all_usage_data(self):
        payload = {'n_items': 30}
        # lots of info in here to be parsed out
        response = self.s.get(API_URL + 'users/%s/timeline' %
                              self.sense_user_id,
                              headers=self.headers, timeout=API_TIMEOUT,
                              data=payload)
        return response.json()
