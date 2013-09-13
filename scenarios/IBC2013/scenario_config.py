#!/usr/bin/env python
# -*- coding: utf-8 -*-

#**********************************************************************************************************************#
#              OPEN-SOURCE CLOUD INFRASTRUCTURE FOR ENCODING AND DISTRIBUTION : SCENARIOS
#
#  Project Manager : Bram Tullemans (tullemans@ebu.ch)
#  Main Developer  : David Fischer (david.fischer.ch@gmail.com)
#  Copyright       : Copyright (c) 2012-2013 EBU. All rights reserved.
#
#**********************************************************************************************************************#
#
# This file is part of EBU Technology & Innovation OSCIED Project.
#
# This project is free software: you can redistribute it and/or modify it under the terms of the EUPL v. 1.1 as provided
# by the European Commission. This project is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
# without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
#
# See the European Union Public License for more details.
#
# You should have received a copy of the EUPL General Public License along with this project.
# If not, see he EUPL licence v1.1 is available in 22 languages:
#     22-07-2013, <https://joinup.ec.europa.eu/software/page/eupl/licence-eupl>
#
# Retrieved from https://github.com/ebu/OSCIED

u"""
Configuration of the demo scenario shown during the International Broadcasting Convention at RAI Amsterdam in 2013.

TODO

"""

import os
from library.oscied_lib.oscied_constants import SERVICE_TO_LABEL
from library.oscied_lib.oscied_juju import ServiceStatistics
from library.oscied_lib.pyutils.py_collections import EventsTable

SCENARIO_PATH = os.path.abspath(os.path.expanduser(os.path.dirname(__file__)))
CHARTS_PATH = os.path.join(SCENARIO_PATH, 'charts')
STATISTICS_PATH = os.path.join(SCENARIO_PATH, 'statistics')

# Simulated hour : An hour that correspond to 1/TIME_SPEEDUP 'real-time' hours.
ENABLE_UNITS_API = True
ENABLE_TESTING = False
TIME_RANGE = 24  # Simulated hours
TIME_SPEEDUP = TIME_RANGE * 60 if ENABLE_TESTING else 12  # How many times per 'real-time' day the scenario will 'loop'
DAEMONS_CHECKS_PER_HOUR = 12  # how many checks per simulated hour (3600 / 12 / 12 = every 25 'real-time' seconds)
STATISTICS_MAXLEN = 30 * DAEMONS_CHECKS_PER_HOUR # Simulated hours

CONFIG_AMAZ = os.path.join(SCENARIO_PATH, u'config_amazon.yaml')
EVENTS_AMAZ = EventsTable({
     0: {u'oscied-transform': 5, u'oscied-publisher': 0},
     8: {u'oscied-transform': 0, u'oscied-publisher': 0},
    17: {u'oscied-transform': 0, u'oscied-publisher': 2},
    18: {u'oscied-transform': 3, u'oscied-publisher': 2},
    20: {u'oscied-transform': 3, u'oscied-publisher': 2},
    23: {u'oscied-transform': 3, u'oscied-publisher': 2}
}, TIME_RANGE, TIME_SPEEDUP, sleep_factor=DAEMONS_CHECKS_PER_HOUR)


CONFIG_MAAS = os.path.join(SCENARIO_PATH, u'config_maas.yaml')
EVENTS_MAAS = EventsTable({
    0: {u'oscied-transform': 4, u'oscied-publisher': 2}
}, TIME_RANGE, TIME_SPEEDUP, sleep_factor=DAEMONS_CHECKS_PER_HOUR)


def read_or_default(environment, service, **kwargs):
    label = SERVICE_TO_LABEL.get(service, service)
    filename = os.path.join(STATISTICS_PATH, u'{0}_{1}.pkl'.format(environment, label))
    statistics = ServiceStatistics.read(filename, store_filename=True, create_if_error=True,
                                        environment=environment, service=service, **kwargs)
    print(u'Read {0} with {1} measures.'.format(os.path.basename(filename), len(statistics.units_planned)))
    if statistics.unknown_states:
        print(u'[WARNING] Unknown states: {0}.'.format(statistics.unknown_states))
    return statistics


STATS_AMAZ, STATS_MAAS = {}, {}
for service in (u'oscied-transform', u'oscied-publisher'):
    STATS_AMAZ[service] = read_or_default(u'amazon', service, maxlen=STATISTICS_MAXLEN)
    STATS_MAAS[service] = read_or_default(u'maas',   service, maxlen=STATISTICS_MAXLEN)


TRANSFORM_MATRIX = ((u'CHSRF-Lausanne_Mens_200m-50368e4c43ca3', u'Tablet 480p/25'),
                    (u'EBU-2013_668629-dv25-1',                 u'Tablet DASH'),)
TRANSFORM_MAX_PENDING_TASKS = 5
MAX_OUTPUT_MEDIA_ASSETS = 15
