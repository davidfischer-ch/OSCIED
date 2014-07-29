# -*- encoding: utf-8 -*-

#**********************************************************************************************************************#
#              OPEN-SOURCE CLOUD INFRASTRUCTURE FOR ENCODING AND DISTRIBUTION : COMMON LIBRARY
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

from __future__ import absolute_import, division, print_function, unicode_literals

import logging, pygal, os, random, shutil, string, threading, time
from os.path import join
from collections import defaultdict, deque

from pytoolbox import juju as py_juju
from pytoolbox.collections import pygal_deque
from pytoolbox.console import confirm
from pytoolbox.datetime import datetime_now
from pytoolbox.encoding import to_bytes
from pytoolbox.mongo import TaskModel
from pytoolbox.juju import ERROR_STATES, juju_do, SimulatedUnits
from pytoolbox.serialization import PickleableObject
from requests.exceptions import ConnectionError, Timeout

from library.oscied_lib.constants import (
    ENVIRONMENT_TO_LABEL, ENVIRONMENT_TO_TYPE, SERVICE_TO_LABEL, SERVICE_TO_UNITS_API, SERVICE_TO_TASKS_API
)
from library.oscied_lib.juju import OsciedEnvironment
from library.oscied_lib.models import Media


class IBCEnvironment(OsciedEnvironment):

    def __init__(self, name, events=None, statistics=None, charts_path=None, enable_units_api=False,
                 enable_units_status=True, enable_tasks_status=True, daemons_auth=None, transform_matrix=None,
                 transform_max_pending_tasks=5, max_output_media_assets=15, **kwargs):
        super(IBCEnvironment, self).__init__(name, **kwargs)
        self.events = events
        self.statistics = statistics
        self.charts_path = charts_path
        self.enable_units_api = enable_units_api
        self.enable_units_status = enable_units_status
        self.enable_tasks_status = enable_tasks_status
        self.daemons_auth = daemons_auth
        self.transform_matrix = transform_matrix
        self.transform_max_pending_tasks = transform_max_pending_tasks
        self.max_output_media_assets = max_output_media_assets
        self._statistics_thread = self._scaling_thread = self._tasks_thread = None

    @property
    def scaling_thread(self):
        if not self._scaling_thread:
            self._scaling_thread = ScalingThread(u'{0} SCALING THREAD'.format(self.name.upper()), self)
        return self._scaling_thread

    @property
    def statistics_thread(self):
        if not self._statistics_thread:
            self._statistics_thread = StatisticsThread(u'{0} STATISTICS THREAD'.format(self.name.upper()), self)
        return self._statistics_thread

    @property
    def tasks_thread(self):
        if not self._tasks_thread:
            self._tasks_thread = TasksThread(u'{0} TASKS THREAD'.format(self.name.upper()), self)
        return self._tasks_thread

    @property
    def threads(self):
        return filter(None, [self._statistics_thread, self._scaling_thread, self._tasks_thread])


class IBCEnvironmentThread(threading.Thread):

    def __init__(self, name, environment, daemon=True):
        super(IBCEnvironmentThread, self).__init__()
        self.name = name
        self.environment = environment
        self.daemon = daemon

    def sleep(self):
        now = datetime_now(format=None)
        sleep_time = self.environment.events.sleep_time(now)
        print(u'[{0}] Sleep {1} seconds ...'.format(self.name, sleep_time))
        time.sleep(sleep_time)


class ServiceStatistics(PickleableObject):
    u"""Store statistics about a service."""

    def __init__(self, environment=None, service=None, time=None, units_planned=None, units_current=None,
                 tasks_current=None, unknown_states=None, maxlen=100, simulate=False,
                 simulated_units_start_latency_range=None, simulated_units_stop_latency_range=None,
                 simulated_tasks_per_unit_range=None, simulated_tasks_divider=None):
        self.environment, self.service = environment, service
        self.time = time or deque(maxlen=maxlen)
        self.units_planned = units_planned or pygal_deque(maxlen=maxlen)
        self.units_current = units_current or {state: pygal_deque(maxlen=maxlen) for state in py_juju.ALL_STATES}
        self.tasks_current = tasks_current or {status: pygal_deque(maxlen=maxlen) for status in self.tasks_status}
        self.unknown_states = defaultdict(int)
        self.simulate = simulate
        self.simulated_units = SimulatedUnits(simulated_units_start_latency_range or (10, 13),
                                              simulated_units_stop_latency_range or (1, 2))
        self.simulated_tasks_per_unit_range = simulated_tasks_per_unit_range or (2, 3)
        self.simulated_tasks_divider = simulated_tasks_divider or self.simulated_tasks_per_unit_range[1]
        self.simulated_tasks_progress = 0

    @property
    def environment_label(self):
        return ENVIRONMENT_TO_LABEL.get(self.environment, self.environment)

    @property
    def environment_type(self):
        return ENVIRONMENT_TO_TYPE.get(self.environment, self.environment)

    @property
    def service_label(self):
        return SERVICE_TO_LABEL.get(self.service, self.service)

    @property
    def tasks_status(self):
        return (TaskModel.PROGRESS,) # TaskModel.PENDING, TaskModel.SUCCESS,

    def update(self, now_string, planned, units=None, tasks=None):

        self.units_planned.append(planned)

        current = defaultdict(int)
        if self.simulate:
            # Retrieve state of all simulated units and update time of 1 tick
            self.simulated_units.ensure_num_units(num_units=planned)
            for unit in self.simulated_units.units.itervalues():
                if unit.state in py_juju.ALL_STATES:
                    current[unit.state] += 1
                else:
                    self.unknown_states[unit.state] += 1
            self.simulated_units.tick()
        elif units:
            # Retrieve agent-state of all units
            for unit in units.itervalues():
                state = unit.get(u'agent-state', u'unknown')
                if state in py_juju.ALL_STATES:
                    current[state] += 1
                else:
                    self.unknown_states[state] += 1
        # Append newest values to the statistics about the units
        for state, history in self.units_current.iteritems():
            history.append(current[state])

        units_started = current[py_juju.STARTED]

        current = defaultdict(int)
        if self.simulate:
            progress = self.simulated_tasks_progress
            target = random.randint(*self.simulated_tasks_per_unit_range) * units_started
            delta = target - progress
            self.simulated_tasks_progress = progress + delta / self.simulated_tasks_divider if units_started > 0 else 0
            current[TaskModel.PROGRESS] = int(self.simulated_tasks_progress)
        elif tasks:
            for task in tasks:
                status = task.status
                if status in TaskModel.PENDING_STATUS:
                    current[TaskModel.PENDING] += 1
                elif status in TaskModel.RUNNING_STATUS:
                    current[TaskModel.PROGRESS] += 1
                elif status in TaskModel.SUCCESS_STATUS:
                    current[TaskModel.SUCCESS] += 1
                # ... else do not add to statistics.
        # Append newest values to the statistics about the tasks
        for status, history in self.tasks_current.iteritems():
            history.append(current[status])
        self.time.append(now_string)

    def _write_own_chart(self, chart, charts_path, prefix, add_x_labels=True):
        filename = u'{0}_{1}_{2}'.format(prefix, self.environment, self.service_label)
        return ServiceStatistics._write_chart(self.time, chart, charts_path, filename, add_x_labels=add_x_labels)

    def generate_units_pie_chart_by_status(self, charts_path, width=300, height=300):
        chart = pygal.Pie(width=width, height=height, no_data_text=u'No unit')
        chart.title = u'Number of {0} {1} nodes'.format(self.environment_type, self.service_label)
        for states in (py_juju.ERROR_STATES, py_juju.STARTED_STATES, py_juju.PENDING_STATES):
            units_number = sum((self.units_current.get(state, pygal_deque()).last or 0) for state in states)
            chart.add(u'{0} {1}'.format(units_number, states[0]), units_number)
        return self._write_own_chart(chart, charts_path, u'pie_units', add_x_labels=False)

    def generate_units_line_chart(self, charts_path, enable_current=True, width=1900, height=300):
        chart = pygal.Line(width=width, height=height, show_dots=True, no_data_text=u'No unit')
        chart.title = u'Number of {0} nodes'.format(self.service_label)
        planned_list, current_list = self.units_planned.list(), self.units_current[py_juju.STARTED].list()
        chart.add(u'{0} planned'.format(planned_list[-1] if len(planned_list) > 0 else 0), planned_list)
        if enable_current:
            chart.add(u'{0} current'.format(current_list[-1] if len(current_list) > 0 else 0), current_list)
        return self._write_own_chart(chart, charts_path, u'line_units')

    def generate_tasks_line_chart(self, charts_path, width=1200, height=300):
        total, lines = 0, {}
        for status in self.tasks_status:
            current_list = self.tasks_current[status].list()
            number = current_list[-1] if len(current_list) > 0 else 0
            total += number
            lines[status] = (number, current_list)
        # , range=(0, total)
        chart = pygal.Line(width=width, height=height, show_dots=True, no_data_text=u'No task')
        chart.title = u'Scheduling of {0} tasks on {1}'.format(self.service_label, self.environment_label)

        for status in self.tasks_status:
            chart.add(u'{0} {1}'.format(lines[status][0], status), lines[status][1])
        return self._write_own_chart(chart, charts_path, u'line_tasks')

    @staticmethod
    def _write_chart(time, chart, charts_path, filename, add_x_labels=True):
        if add_x_labels:
            chart.x_labels = list(time)
            chart.x_labels_major_count = 3
            chart.x_label_rotation = 0
            chart.show_minor_x_labels = False
        chart.label_font_size = chart.major_label_font_size = 12
        chart.explicit_size = True
        chart.order_min = 0
        chart.truncate_label = 20
        chart.truncate_legend = 20
        tmp_file = join(charts_path, u'{0}.new.svg'.format(filename))
        dst_file = join(charts_path, u'{0}.svg'.format(filename))
        chart.render_to_file(tmp_file)
        shutil.copy(tmp_file, dst_file)
        return dst_file

    @staticmethod
    def generate_units_stacked_chart(statistics, charts_path, enable_current=True, width=1900, height=300):
        labels = set(s.service_label for s in statistics)
        if len(labels) != 1:
            raise ValueError(to_bytes(u'Cannot generate a chart of different services, values: {0}'.format(labels)))
        service_label = labels.pop()
        chart = pygal.StackedLine(width=width, height=height, fill=True, show_dots=False, no_data_text=u'No unit')
        chart.title = u'Number of {0} nodes'.format(service_label)
        for statistic in statistics:
            planned_list = statistic.units_planned.list(fill=True)
            current_list = statistic.units_current[py_juju.STARTED].list(fill=True)
            chart.add(statistic.environment_label, planned_list)
        #if enable_current:
        #    TODO
        return ServiceStatistics._write_chart(statistics[0].time, chart, charts_path, u'sum_{0}'.format(service_label))


class ScalingThread(IBCEnvironmentThread):
    u"""Handle the scaling of a deployed OSCIED setup."""

    def run(self):
        while True:
            # Get current time to retrieve state
            env, now, now_string = self.environment, datetime_now(format=None), datetime_now()
            try:
                env.auto = True  # Really better like that ;-)
                index, event = env.events.get(now, default_value={})
                print(u'[{0}] Handle scaling at index {1}.'.format(self.name, index))
                for service, stats in env.statistics.iteritems():
                    label = SERVICE_TO_LABEL.get(service, service)
                    units_api = SERVICE_TO_UNITS_API[service]
                    planned = event.get(service, None)
                    if env.enable_units_api:
                        api_client = env.api_client
                        api_client.auth = env.daemons_auth
                        units = getattr(api_client, units_api).list()
                    else:
                        units = env.get_units(service)
                    if len(units) != planned:
                        print(u'[{0}] Ensure {1} instances of service {2}'.format(self.name, planned, label))
                        env.ensure_num_units(service, service, num_units=planned)
                        env.cleanup_machines()  # Safer way to terminate machines !
                    else:
                        print(u'[{0}] Nothing to do !'.format(self.name))
                    # Recover faulty units
                    # FIXME only once and then destroy and warn admin by mail ...
                    for number, unit_dict in units.iteritems():
                        if unit_dict.get(u'agent-state') in ERROR_STATES:
                            unit = u'{0}/{1}'.format(service, number)
                            juju_do(u'resolved', environment=env.name, options=[u'--retry', unit], fail=False)
            except (ConnectionError, Timeout) as e:
                # FIXME do something here ...
                print(u'[{0}] WARNING! Communication error, details: {1}.'.format(self.name, e))
            self.sleep()


class StatisticsThread(IBCEnvironmentThread):
    u"""Update statistics and generate charts of the deployed OSCIED setups."""

    def run(self):
        while True:
            # Get current time to retrieve state
            env, now, now_string = self.environment, datetime_now(format=None), datetime_now()
            try:
                env.auto = True  # Really better like that ;-)
                index, event = env.events.get(now, default_value={})
                print(u'[{0}] Update charts at index {1}.'.format(self.name, index))
                for service, stats in env.statistics.iteritems():
                    label = SERVICE_TO_LABEL.get(service, service)
                    units_api, tasks_api = SERVICE_TO_UNITS_API[service], SERVICE_TO_TASKS_API[service]
                    planned = event.get(service, None)
                    api_client = env.api_client
                    api_client.auth = env.daemons_auth
                    if env.enable_units_status:
                        if env.enable_units_api:
                            units = getattr(api_client, units_api).list()
                        else:
                            units = env.get_units(service)
                    else:
                        units = {k: {u'agent-state': py_juju.STARTED} for k in range(planned)}
                    tasks = getattr(api_client, tasks_api).list(head=True) if env.enable_tasks_status else None
                    stats.update(now_string, planned, units, tasks)
                    stats.generate_units_pie_chart_by_status(env.charts_path)
                    stats.generate_units_line_chart(env.charts_path)
                    stats.generate_tasks_line_chart(env.charts_path)
                    stats.write()
            except (ConnectionError, Timeout) as e:
                # FIXME do something here ...
                print(u'[{0}] WARNING! Communication error, details: {1}.'.format(self.name, e))
            self.sleep()


class TasksThread(IBCEnvironmentThread):
    u"""Drives a deployed OSCIED setup to transcode, publish and cleanup media assets for demo purposes."""

    @staticmethod
    def get_media_or_raise(medias, media_title):
        u"""Return a media asset with title ``media_title`` or raise an IndexError."""
        try:
            return next(media for media in medias if media.metadata[u'title'] == media_title)
        except StopIteration:
            raise IndexError(to_bytes(u'Missing media asset "{0}".'.format(media_title)))

    @staticmethod
    def get_profile_or_raise(profiles, profile_title):
        u"""Return a transformation profile with title ``profile_title`` or raise an IndexError."""
        try:
            return next(profile for profile in profiles if profile.title == profile_title)
        except StopIteration:
            raise IndexError(to_bytes(u'Missing transformation profile "{0}".'.format(profile_title)))

    @staticmethod
    def launch_transform(api_client, media_in, profile, title_prefix, filename_suffix):
        in_title = media_in.metadata[u'title']
        out_title = u'{0} {1}'.format(title_prefix, in_title)
        metadata = {u'title': out_title, u'profile': profile.title}
        print(u'Transcode "{0}" to "{1}" with profile {2} ...'.format(in_title, out_title, profile.title))
        return api_client.transform_tasks.add({
            u'filename': profile.output_filename(media_in.filename, suffix=filename_suffix),
            u'media_in_id': media_in._id, u'profile_id': profile._id, u'send_email': False,
            u'queue': u'transform', u'metadata': metadata
        })

    def transform(self, api_client):
        u"""Transcode source media assets with chosen profiles limiting amount of pending tasks."""
        medias = api_client.medias.list(head=True, spec={u'status': {u'$ne': Media.DELETED}})
        profiles = api_client.transform_profiles.list()
        tasks = api_client.transform_tasks.list(head=True)
        counter = (self.environment.transform_max_pending_tasks -
                   sum(1 for task in tasks if task.status in TaskModel.PENDING_STATUS))
        if counter <= 0:
            print(u'No need to create any media asset, already {0} pending.'.format(self.output_counter))
        else:
            s = u's' if counter > 1 else u''
            print(u'Launch {0} transcoding task{1} to create media assets.'.format(counter, s))
            for i in range(counter):
                media_title, profile_title = random.choice(self.environment.transform_matrix)
                media = TasksThread.get_media_or_raise(medias, media_title)
                profile = TasksThread.get_profile_or_raise(profiles, profile_title)
                TasksThread.launch_transform(api_client, media, profile,
                                             u'Output {0}'.format(self.output_counter),
                                             u'_output_{0}'.format(self.output_counter))
                self.output_counter += 1

    def cleanup_transform_tasks(self, api_client, auto=False, cleanup_progress_time=20):
        u"""Cleanup transformation tasks that stuck in progress status without updating the eta_time."""
        tasks, new_time = api_client.transform_tasks.list(head=True), time.time()
        progress_tasks = [t for t in tasks if t.status == TaskModel.PROGRESS]
        delta_time = new_time - self.progress_tasks[0]
        if cleanup_progress_time and delta_time > cleanup_progress_time:
            for task in progress_tasks:
                try:
                    prev_task = next(t for t in self.progress_tasks[1] if t._id == task._id)
                    prev_eta_time = prev_task.statistic.get(u'eta_time')
                    eta_time = task.statistic.get(u'eta_time')
                    logging.debug(u'PROGRESS task {0} previous eta_time {1}, current {2}'.format(
                                 task._id, prev_eta_time, eta_time))
                    if eta_time == prev_eta_time:
                        logging.warning(u"PROGRESS task {0} hasn't updated is eta_time for at least {1} seconds.".
                                        format(task._id, delta_time))
                        logging.info(task.__dict__)
                        if auto or confirm(u'Revoke the task now ?'):
                            del api_client.transform_tasks[task._id]
                except StopIteration:
                    pass
        self.progress_tasks = (new_time, progress_tasks)

    def cleanup_media_assets(self, api_client):
        u"""Limit output media assets in shared storage by deleting the oldest."""
        maximum = self.environment.max_output_media_assets
        medias = api_client.medias.list(head=True, sort=[(u'metadata.add_date', 1)])
        output_medias = [m for m in medias if m.status == Media.READY and m.parent_id]
        counter = len(output_medias) - maximum
        if counter <= 0:
            print(u'No need to delete any output media asset, they are {0} ready and limit is {1}.'.format(
                  len(output_medias), maximum))
        else:
            s = u's' if counter > 1 else u''
            print(u'Delete {0} output media asset{1} to keep at most {2} of them.'.format(counter, s, maximum))
            for i in range(counter):
                media = output_medias.pop()
                print(u'Delete output media asset "{0}".'.format(media.metadata[u'title']))
                assert(media.parent_id)
                del api_client.medias[media._id]

    def run(self):
        self.output_counter = 0
        self.progress_tasks = (time.time(), [])
        while True:
            # Get current time to retrieve state
            now, now_string = datetime_now(format=None), datetime_now()
            try:
                self.environment.auto = True  # Really better like that ;-)
                api_client = self.environment.api_client
                api_client.auth = self.environment.daemons_auth
                self.transform(api_client)
                self.cleanup_transform_tasks(api_client, auto=True, cleanup_progress_time=60)
                self.cleanup_media_assets(api_client)

            except (ConnectionError, Timeout) as e:
                # FIXME do something here ...
                print(u'[{0}] WARNING! Communication error, details: {1}.'.format(self.name, e))
            self.sleep()
