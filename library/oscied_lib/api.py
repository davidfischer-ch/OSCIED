#!/usr/bin/env python
# -*- coding: utf-8 -*-

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

from __future__ import absolute_import

import logging, mongomock, os, pymongo, re, smtplib, uuid
from celery.task.control import revoke
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from flask import abort
from jinja2 import Template
from pymongo.errors import DuplicateKeyError
from random import randint
from requests import get, patch, post, delete

from . import PublisherWorker, TransformWorker
from .config_test import ORCHESTRA_CONFIG_TEST
from .models import Media, User, TransformProfile, PublisherTask, TransformTask, ENCODERS_NAMES
from .utils import Callback, Storage
from .plugit_api import PlugItAPI
from .pytoolbox import juju
from .pytoolbox.datetime import datetime_now
from .pytoolbox.encoding import csv_reader, to_bytes
from .pytoolbox.flask import json_response, map_exceptions
from .pytoolbox.juju import get_unit_path, juju_do
from .pytoolbox.pyutils import UUID_ZERO
from .pytoolbox.serialization import dict2object, object2dict, object2json
from .pytoolbox.subprocess import rsync, ssh
from .pytoolbox.validation import valid_uuid

ABOUT = u"Orchestra : EBU's OSCIED Orchestrator by David Fischer 2012-2013"


class OsciedCRUDMapper(object):

    def __init__(self, api_client, method=u'', cls=None, id_prefix=u'id', environment=False):
        self.api_client = api_client
        self.method = method
        self.cls = cls
        self.id_prefix = id_prefix
        self.environment = environment

    def get_url(self, index=None, extra=None):
        environment = u'environment/{0}'.format(self.api_client.environment) if self.environment else u''
        index = u'{0}/{1}'.format(self.id_prefix, index) if index else None
        return u'/'.join(filter(None, [self.api_client.api_url, self.method, environment, index, extra]))

    def __len__(self):
        return self.api_client.do_request(get, self.get_url(extra=u'count'))

    def __getitem__(self, index):
        response_dict = self.api_client.do_request(get, self.get_url(index))
        return response_dict if self.cls is None else dict2object(self.cls, response_dict, inspect_constructor=True)

    def __setitem__(self, index, value):
        return self.api_client.do_request(patch, self.get_url(index), data=object2json(value, include_properties=True))

    def __delitem__(self, index):
        return self.api_client.do_request(delete, self.get_url(index))

    def __contains__(self, value):
        if hasattr(value, u'_id'):
            value = value._id
        try:
            return self.api_client.do_request(get, self.get_url(value))
        except:
            return False
        return True

    def add(self, *args, **kwargs):
        if not(bool(args) ^ bool(kwargs)):
            raise ValueError(to_bytes(u'You must set args OR kwargs.'))
        if args and len(args) != 1:
            raise ValueError(to_bytes(u'args should contain only 1 value.'))
        value = args[0] if args else kwargs
        response = self.api_client.do_request(post, self.get_url(), data=object2json(value, include_properties=False))
        instance = dict2object(self.cls, response, inspect_constructor=True) if self.cls else response
        # Recover user's secret
        if isinstance(instance, User):
            instance.secret = value.secret if args else kwargs[u'secret']
        return instance

    def count(self, **data):
        return self.api_client.do_request(get, self.get_url(extra=u'count'),
                                          data=object2json(data, include_properties=False))

    def list(self, head=False, **data):
        values = []
        response_dict = self.api_client.do_request(get, self.get_url(extra=(u'HEAD' if head else None)),
                                                   data=object2json(data, include_properties=False))
        if self.cls is None:
            return response_dict
        for value_dict in response_dict:
            values.append(dict2object(self.cls, value_dict, inspect_constructor=True))
        return values


# ----------------------------------------------------------------------------------------------------------------------

class OrchestraAPIClient(object):

    def __init__(self, hostname, port=5000, api_unit=u'oscied-orchestra/0', api_local_config=u'local_config.pkl',
                 auth=None, id_rsa=u'~/.ssh/id_rsa', environment=u'default', timeout=10.0):
        self.api_url = u'{0}:{1}'.format(hostname, port)
        self.api_unit = api_unit
        self.api_local_config = api_local_config
        self.auth = auth
        self.root_auth = auth if (auth is not None and not isinstance(auth, User) and auth[0] == u'root') else None
        self.id_rsa = os.path.abspath(os.path.expanduser(id_rsa))
        self.environment = environment
        self.timeout = timeout
        self.storage_path = self.storage_address = self.storage_mountpoint = None
        self.users = OsciedCRUDMapper(self, u'user', User)
        self.medias = OsciedCRUDMapper(self, u'media', Media)
        self.environments = OsciedCRUDMapper(self, u'environment', None, u'name')
        self.transform_profiles = OsciedCRUDMapper(self, u'transform/profile', TransformProfile)
        self.transform_units = OsciedCRUDMapper(self, u'transform/unit', None, u'number', True)
        self.transform_tasks = OsciedCRUDMapper(self, u'transform/task', TransformTask)
        self.publisher_units = OsciedCRUDMapper(self, u'publisher/unit', None, u'number', True)
        self.publisher_tasks = OsciedCRUDMapper(self, u'publisher/task', PublisherTask)
        # FIXME api_transform_unit_number_get, api_transform_unit_number_delete ...

    # Miscellaneous methods of the API ---------------------------------------------------------------------------------

    @property
    def about(self):
        return self.do_request(get, self.api_url)

    def flush(self):
        return self.do_request(post, u'{0}/flush'.format(self.api_url))

    def login(self, user_or_mail, secret=None, update_auth=True):
        if isinstance(user_or_mail, User):
            auth = user_or_mail.credentials
        elif secret is not None:
            auth = (user_or_mail, secret)
        else:
            raise ValueError(to_bytes(u'User_or_mail is neither a valid instance of User nor a mail with a secret '
                                      'following.'))
        user_dict = self.do_request(get, u'{0}/user/login'.format(self.api_url), auth)
        user = dict2object(User, user_dict, inspect_constructor=True)
        if update_auth:
            # Recover user's secret
            user.secret = auth[1]
            self.auth = user
        return user

    def login_or_add(self, user):
        u"""Return logged ``user`` and take care of adding this ``user`` if login is not successful (as root)."""
        try:
            return self.login(user)
        except:
            self.auth = self.root_auth
            self.auth = self.users.add(user)
            return self.auth

    @property
    def encoders(self):
        return self.do_request(get, u'{0}/transform/profile/encoder'.format(self.api_url))

    @property
    def transform_queues(self):
        return self.do_request(get, u'{0}/transform/queue'.format(self.api_url))

    @property
    def publisher_queues(self):
        return self.do_request(get, u'{0}/publisher/queue'.format(self.api_url))

    # ------------------------------------------------------------------------------------------------------------------

    def do_request(self, verb, resource, auth=None, data=None):
        u"""Execute a method of the API."""
        headers = {u'Content-type': u'application/json', u'Accept': u'application/json'}
        auth = auth or self.auth
        auth = auth.credentials if isinstance(auth, User) else auth
        url = u'http://{0}'.format(resource)
        return map_exceptions(verb(url, auth=auth, data=data, headers=headers, timeout=self.timeout).json())

    # More complex methods not directly related to the API -------------------------------------------------------------

    def get_unit_local_config(self, service, number, local_config=u'local_config.pkl', option=None):
        u"""Parse local_config.pkl of a actually running charm instance !"""
        # Example : sS'storage_address' p29 S'ip-10-245-189-174.ec2.internal' p30
        # FIXME use test vector (OSCIED note on lastpass) to unit-test get_unit_local_config
        value = juju_do(u'ssh', environment=self.environment, options=[
            u'{0}/{1}'.format(service, number), u'sudo cat {0}'.format(get_unit_path(service, number, local_config))])
        if not option:
            return value
        try:
            return re.findall(ur".*S'{0}' p[0-9]+ .'*([^ ']*)".format(option), value, re.DOTALL | re.MULTILINE)[0]
        except:
            return None
        # from tempfile import NamedTemporaryFile
        # f = NamedTemporaryFile(delete=False)
        # try:
        #     f.write(value)
        #     import pickle
        #     f.seek(0)
        #     p = pickle.load(f)
        #     f.close()
        # finally:
        #     os.remove(f.name)

    def upload_media(self, filename):
        u"""Upload a media asset by rsync-ing the local file to the shared storage mount point of the orchestrator !"""
        # FIXME detect name based on hostname ?
        os.chmod(self.id_rsa, 0600)
        service, number = self.api_unit.split(u'/')
        host = u'ubuntu@{0}'.format(self.api_url.split(u':')[0])

        cfg, get = self.api_local_config, self.get_unit_local_config
        if self.environment == u'maas':
            p = self.storage_path = u'/mnt/storage'
            a = self.storage_address = u'192.168.0.9'
            m = self.storage_mountpoint = u'medias_volume_0'
        else:
            p = self.storage_path       = self.storage_path       or get(service, number, cfg, option=u'storage_path')
            a = self.storage_address    = self.storage_address    or get(service, number, cfg, option=u'storage_address')
            m = self.storage_mountpoint = self.storage_mountpoint or get(service, number, cfg, option=u'storage_mountpoint')
        bkp_path = os.path.join(p, u'uploads_bkp/')
        dst_path = os.path.join(p, u'uploads/')

        print(rsync(filename, u'{0}:{1}'.format(host, bkp_path), makedest=True, archive=True, progress=True,
              rsync_path=u'sudo rsync', extra='ssh -i {0}'.format(self.id_rsa))['stdout'])
        sync_bkp_to_upload = u'sudo rsync -ah --progress {0} {1}'.format(bkp_path, dst_path)
        print(ssh(host, id=self.id_rsa, remote_cmd=sync_bkp_to_upload)['stdout'])
        ssh(host, id=self.id_rsa, remote_cmd=u'sudo chown www-data:www-data {0} -R'.format(dst_path))

        return u'{0}://{1}/{2}/uploads/{3}'.format(u'glusterfs', a, m, os.path.basename(filename))

    def remove_medias(self):
        u"""Remove all medias from the shared storage mount point of the orchestrator !"""
        # FIXME detect name based on hostname ?
        os.chmod(self.id_rsa, 0600)
        service, number = self.api_unit.split(u'/')
        host = u'ubuntu@{0}'.format(self.api_url.split(u':')[0])

        cfg, get = self.api_local_config, self.get_unit_local_config
        if self.environment == u'maas':
            p = self.storage_path = u'/mnt/storage'
        else:
            p = self.storage_path = self.storage_path or get(service, number, cfg, option=u'storage_path')
        medias_path = os.path.join(p, u'medias/*')

        ssh(host, id=self.id_rsa, remote_cmd=u'sudo rm -rf {0}'.format(medias_path))


# ----------------------------------------------------------------------------------------------------------------------

class OrchestraAPICore(object):

    # <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<< Constructor >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>

    def __init__(self, config):
        self.config = config
        if self.is_mock:
            self._db = mongomock.Connection().orchestra
        else:
            self._db = pymongo.Connection(config.mongo_admin_connection)[u'orchestra']
        self.config_db()
        self.root_user = User(first_name=u'root', last_name=u'oscied', mail=u'root@oscied.org',
                              secret=self.config.root_secret, admin_platform=True, _id=UUID_ZERO)
        self.node_user = User(first_name=u'node', last_name=u'oscied', mail=u'node@oscied.org',
                              secret=self.config.node_secret, admin_platform=False, _id=UUID_ZERO)

    # <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<< Properties >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>

    @property
    def about(self):
        return ABOUT

    @property
    def db_count_keys(self):
        return (u'spec',)

    @property
    def db_find_keys(self):
        return (u'spec', u'fields', u'limit', u'skip', u'sort')

    @property
    def db_find_options(self):
        return {'timeout': True, 'snapshot': False}  # FIXME E12001 can't sort with $snapshot

    @property
    def is_mock(self):
        return not self.config.mongo_admin_connection

    @property
    def is_standalone(self):
        return self.config.plugit_api_url is None or not self.config.plugit_api_url.strip()

    @property
    def plugit_api(self):
        return None if self.is_standalone else PlugItAPI(self.config.plugit_api_url)

    # <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<< Functions >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>

    def config_db(self):
        self._db.users.ensure_index('mail', unique=True)
        self._db.medias.ensure_index('uri', unique=True)
        self._db.transform_profiles.ensure_index('title', unique=True)

    def flush_db(self):
        for collection in (u'users', u'medias', u'transform_profiles', u'transform_tasks', u'publisher_tasks'):
            self._db.drop_collection(collection)
        self.config_db()
        logging.info(u"Orchestra database's collections dropped !")

    def only_standalone(self):
        if not self.is_standalone:
            raise RuntimeError(to_bytes(u'This method is only available in standalone mode.'))

    def send_email(self, to_addresses, subject, text_plain, text_html=None):
        if not self.config.email_server:
            logging.debug(u'E-mail delivery is disabled in configuration.')
            return {}
        part1 = MIMEText(text_plain, u'plain')
        part2 = MIMEText(text_html, u'html') if text_html else None
        msg = part1 if not part2 else MIMEMultipart(u'alternative')
        msg[u'Subject'] = subject
        msg[u'From'] = self.config.email_address
        msg[u'To'] = u', '.join(to_addresses) if isinstance(to_addresses, dict) else to_addresses
        if part2:
            msg.attach(part1)
            msg.attach(part2)
        try:
            server = smtplib.SMTP(self.config.email_server)
            if self.config.email_tls:
                server.starttls()
            server.login(self.config.email_username, self.config.email_password)
            result = server.sendmail(self.config.email_address, to_addresses, msg.as_string())
            logging.info(u'E-mail delivery {0}, result {1}'.format(msg, result))
            return result
        finally:
            server.quit()

    def send_email_task(self, task, status, media=None, media_out=None):
        if task.send_email:
            user = self.get_user({u'_id': task.user_id}, {u'mail': 1})
            if not user:
                raise IndexError(to_bytes(u'Unable to find user with id {0}.'.format(task.user_id)))
            if isinstance(task, TransformTask):
                media_in = self.get_media({u'_id': task.media_in_id})
                if not media_in:
                    # FIXME maybe do not raise but put default value or return ?
                    raise IndexError(to_bytes(u'Unable to find input media asset with id {0}.'.format(
                                     task.media_in_id)))
                profile = self.get_transform_profile({u'_id': task.profile_id})
                if not profile:
                    # FIXME maybe do not raise but put default value or return ?
                    raise IndexError(to_bytes(u'Unable to find transformation profile with id {0}.'.format(
                                     task.profile_id)))
                task.load_fields(user, media_in, media_out, profile)
                template, name = self.config.email_ttask_template, u'Transformation'
            elif isinstance(task, PublisherTask):
                task.load_fields(user, media)
                template, name = self.config.email_ptask_template, u'Publication'
            else:
                return  # FIXME oups
            task.append_async_result()
            with open(template, u'r', u'utf-8') as template_file:
                text_plain = Template(template_file.read()).render(object2dict(task, include_properties=True))
                # FIXME YourFormatter().format(template_file.read(), task)
            self.send_email(task.user.mail, u'OSCIED - {0} task {1} {2}'.format(name, task._id, status), text_plain)

    def ok_200(self, value, include_properties):
        if self.is_standalone:
            # FIXME include_properties not yet handled
            return {u'status': 200, u'value': value}
        return json_response(200, value=value, include_properties=include_properties)

    # http://publish.luisrei.com/articles/flaskrest.html
    def requires_auth(self, request, allow_root=False, allow_node=False, allow_any=False, role=None, id=None,
                      mail=None):
        """
        This method implements Orchestra's RESTful API (standalone only) authentication logic. Here is ensured that an
        access to a method of the API is filtered based on rules (this method's parameters). HTTP user agent must
        authenticate through HTTP basic access authentication. The username must be user's email address and password
        must be user's secret. This not apply for system-users like root or node as they do not have any e-mail address.

        .. warning::

            Username and password are passed as plaintext, SSL/TLS is one of the way to improve security although this was
            not tested during my thesis.

        This method will abort request with HTTP 401 error if HTTP user agent doesn't authenticate.

        :param request: the request itself, credentials are retrieved from request authorization header
        :param allow_root: if set to `True` root system-user will be allowed
        :param allow_node: if set to `True` node system-user will be allowed
        :param allow_any: if set to `True` any authenticated user will be allowed
        :param role: if set to <name>, any user will "name" role set to `True` will be allowed
        :param id: if set to <uuid>, any user with _id equal to "uuid" will be allowed
        :param mail: if set to <mail>, any user with mail equal to "mail" will be allowed

        This method will abort request with HTTP 403 error if none of the following conditions are met.

        Example::

            # Allow any authenticated user
            @action(u'/my/example/route', methods=[u'GET'])
            def api_my_example_route():
                if request.method == u'GET':
                    auth_user = orchestra.requires_auth(request=request, allow_any=True)
                    ...
                    return ok_200(u'my return value', True)

            # Allow root system-user or any user with admin attribute set
            @action(u'/my/restricted/route', methods=[u'GET'])
            def api_my_restricted_route():
                if request.method == u'GET':
                    auth_user = orchestra.requires_auth(request=request, allow_root=True, allow_role='admin')
                    ...
                    return ok_200(u'my return value', True)
        """
        if not self.is_standalone:
            return  # Bypass user authentication & authorization if not in standalone mode.
        auth = request.authorization
        if not auth or auth.username is None or auth.password is None:
            abort(401, u'Authenticate.')  # Testing for None is maybe too much ... Security is like that
        username = auth.username
        password = auth.password
        root = (username == u'root' and password == self.config.root_secret)
        node = (username == u'node' and password == self.config.node_secret)
        user = None
        if not root and not node:
            user = self.get_user({u'mail': username}, secret=password)
            username = user.name if user else None
        if not root and not user and not node:
            abort(401, u'Authentication Failed.')
        if root and allow_root:
            logging.info(u'Allowed authenticated root')
            return self.root_user
        if node and allow_node:
            logging.info(u'Allowed authenticated worker/node')
            return self.node_user
        if user and allow_any:
            logging.info(u'Allowed authenticated user {0}'.format(user.name))
            return user
        if role and hasattr(user, role) and getattr(user, role):
            logging.info(u'Allowed authenticated user {0} with role {1}'.format(user.name, role))
            return user
        if id and user._id == id:
            logging.info(u'Allowed authenticated user {0} with id {1}'.format(user.name, id))
            return user
        if mail and user.mail == mail:
            logging.info(u'Allowed authenticated user {0} with mail {1}'.format(user.name, mail))
            return user
        abort(403, username)

    # ------------------------------------------------------------------------------------------------------------------

    def save_user(self, user, hash_secret):
        self.only_standalone()
        user.is_valid(True)
        if hash_secret:
            user.hash_secret()
        try:
            self._db.users.save(user.__dict__, safe=True)
        except DuplicateKeyError:
            raise ValueError(to_bytes(u'The email address {0} is already used by another user.'.format(user.mail)))

    def get_user(self, spec, fields=None, secret=None):
        self.only_standalone()
        entity = self._db.users.find_one(spec, fields)
        if not entity:
            return None
        user = dict2object(User, entity, inspect_constructor=True)
        return user if secret is None or user.verify_secret(secret) else None

    def delete_user(self, user):
        self.only_standalone()
        # FIXME issue #16 (https://github.com/ebu/OSCIED/issues/16)
        # entity = self.get_user({'_id': user_id}, {'secret': 0})
        # if not entity:
        #     raise IndexError(to_bytes(u'No user with id {0}.'.format(id)))
        # self._db.users.remove({'_id': entity._id})
        # return dict2object(User, entity, inspect_constructor=True)
        if valid_uuid(user, none_allowed=False):
            user = self.get_user({u'_id': user}, {u'secret': 0})
        user.is_valid(True)
        self._db.users.remove({u'_id': user._id})

    def get_users(self, spec=None, fields=None, skip=0, limit=0, sort=None):
        self.only_standalone()
        if fields is not None:
            fields[u'secret'] = 0  # Disable access to users secret !
        users, sort = [], sort or [(u'last_name', 1), (u'first_name', 1)]  # Sort by default, this is nicer like that !
        for entity in list(self._db.users.find(spec=spec, fields=fields, skip=int(skip), limit=int(limit), sort=sort,
                                               **self.db_find_options)):
            user = dict2object(User, entity, inspect_constructor=True)
            users.append(user)
        return users

    def get_users_count(self, spec=None):
        self.only_standalone()
        return self._db.users.find(spec, {u'_id': 1}).count()

    # ------------------------------------------------------------------------------------------------------------------

    def save_media(self, media):
        media.is_valid(True)
        if not media.get_metadata(u'title'):
            raise ValueError(to_bytes(u"Title key is required in media asset's metadata."))
        if media.status != Media.DELETED:
            if self.is_mock:
                size = randint(10*1024*1024, 10*1024*1024*1024)
                duration = u'%02d:%02d:%02d' % (randint(0, 2), randint(0, 59), randint(0, 59))
            else:
                size, duration = Storage.add_media(self.config, media)
        else:
            size, duration = (0, 0)
        media.add_metadata(u'size', size, True)
        if duration:
            media.add_metadata(u'duration', duration, True)
        media.add_metadata(u'add_date', datetime_now(), True)
        try:
            self._db.medias.save(media.__dict__, safe=True)
        except DuplicateKeyError:
            raise ValueError(to_bytes(u'The media URI {0} is already used by another media asset.'.format(media.uri)))

    def get_media(self, spec, fields=None, load_fields=False):
        entity = self._db.medias.find_one(spec, fields)
        if not entity:
            return None
        media = dict2object(Media, entity, inspect_constructor=True)
        if load_fields:
            media.load_fields(self.get_user({u'_id': media.user_id}, {u'secret': 0}),
                              self.get_media({u'_id': media.parent_id}))

        # Add read path to the media asset
        media.api_uri = self.config.storage_medias_path(media, generate=False)

        return media

    def delete_media(self, media):
        if valid_uuid(media, none_allowed=False):
            media = self.get_media({u'_id': media})
        media.is_valid(True)
        task = self.get_transform_task({u'media_in_id': media._id}, append_result=True)
        if task and task.status in TransformTask.WORK_IN_PROGRESS_STATUS:
            raise ValueError(to_bytes(u'Cannot delete the media asset, it is actually in use by transformation task wit'
                             'h id {0} and status {1}.'.format(task._id, task.status)))
        task = self.get_publisher_task({u'media_id': media._id}, append_result=True)
        if task and task.status in TransformTask.WORK_IN_PROGRESS_STATUS:
            raise ValueError(to_bytes(u'Cannot delete the media asset, it is actually in use by publication task with i'
                             'd {0} and status {1}.'.format(task._id, task.status)))
        media.status = Media.DELETED
        self.save_media(media)
        #self._db.medias.remove({'_id': media._id})
        Storage.delete_media(self.config, media)

    def get_medias(self, spec=None, fields=None, skip=0, limit=0, sort=None, load_fields=False):
        medias, sort = [], sort or [('metadata.title',  1)]  # Sort by default, this is nicer like that !
        for entity in list(self._db.medias.find(spec=spec, fields=fields, skip=int(skip), limit=int(limit), sort=sort,
                                                **self.db_find_options)):
            media = dict2object(Media, entity, inspect_constructor=True)
            if load_fields:
                media.load_fields(self.get_user({u'_id': media.user_id}, {u'secret': 0}),
                                  self.get_media({u'_id': media.parent_id}))
            medias.append(media)
        return medias

    def get_medias_count(self, spec=None):
        return self._db.medias.find(spec, {u'_id': 1}).count()

    # ------------------------------------------------------------------------------------------------------------------

    def add_environment(self, name, type, region, access_key, secret_key, control_bucket, test=False):
        if not test:
            raise NotImplementedError(u'This method is in development, set test to True to disable this warning.')
        return juju.add_environment(name, type, region, access_key, secret_key, control_bucket,
                                    self.config.charms_release, environments=self.config.juju_config_file)

    def delete_environment(self, name, remove=False):
        u"""
        .. warning:: TODO test & debug of environment methods, especially delete !
        """
        return juju.destroy_environment(name, remove_default=False, remove=remove,
                                        environments=self.config.juju_config_file)

    def get_environment(self, name, get_status=False):
        return juju.get_environment(name, get_status=get_status, environments=self.config.juju_config_file)

    def get_environments(self, get_status=False):
        return juju.get_environments(get_status=get_status, environments=self.config.juju_config_file)

    # ------------------------------------------------------------------------------------------------------------------

    def get_transform_profile_encoders(self):
        return ENCODERS_NAMES

    def save_transform_profile(self, profile):
        profile.is_valid(True)
        # FIXME exact matching !
        try:
            self._db.transform_profiles.save(profile.__dict__, safe=True)
        except DuplicateKeyError:
            raise ValueError(to_bytes(u'The title {0} is already used by another transformation profile.'.format(
                             profile.title)))

    def get_transform_profile(self, spec, fields=None):
        entity = self._db.transform_profiles.find_one(spec, fields)
        if not entity:
            return None
        return dict2object(TransformProfile, entity, inspect_constructor=True)

    def delete_transform_profile(self, profile):
        if valid_uuid(profile, none_allowed=False):
            profile = self.get_profile({u'_id': profile})
        profile.is_valid(True)
        self._db.transform_profiles.remove({u'_id': profile._id})

    def get_transform_profiles(self, spec=None, fields=None, skip=0, limit=0, sort=None):
        profiles, sort = [], sort or [('encoder_name', 1), ('title',  1)]  # Sort by default, this is nicer like that !
        for entity in list(self._db.transform_profiles.find(spec=spec, fields=fields, skip=int(skip), limit=int(limit),
                                                            sort=sort, **self.db_find_options)):
            profiles.append(dict2object(TransformProfile, entity, inspect_constructor=True))
        return profiles

    def get_transform_profiles_count(self, spec=None):
        return self._db.transform_profiles.find(spec, {u'_id': 1}).count()

    # ------------------------------------------------------------------------------------------------------------------

    def ensure_num_transform_units(self, environment, num_units, terminate, test=False):
        u"""

        .. warning::

            FIXME implement more robust resources listing and removing, sometimes juju fail during a call
            (e.g. destroy_transform_units with num_units=10) and then some machines are not destroyed.

            * implement a garbage collector method callable by user when he want to destroy useless machines ?
            * implement a thread to handle removing unit asynchronously.
        """
        if not test:
            raise NotImplementedError(u'This method is in development, set test to True to disable this warning.')
        environments, default = self.get_environments()
        if environment == 'default':
            environment = default
        same_environment = (environment == default)
        config = juju.load_unit_config(self.config.transform_config)
        config[u'rabbit_queues'] = u'transform_{0}'.format(environment)
        if not same_environment:
            raise NotImplementedError(to_bytes(u'Unable to setup transformation units into non-default environment {0} '
                                      '(default is {1}).'.format(environment, default)))
            config[u'mongo_connection'] = self.config.mongo_node_connection
            config[u'rabbit_connection'] = self.config.rabbit_connection
            # FIXME copy storage configuration, first method
            config[u'storage_address'] = self.config.storage_address
            config[u'storage_fstype'] = self.config.storage_fstype
            config[u'storage_mountpoint'] = self.config.storage_mountpoint
            config[u'storage_options'] = self.config.storage_options
        juju.save_unit_config(self.config.charms_config, self.config.transform_service, config)
        juju.ensure_num_units(environment, self.config.transform_service, num_units=num_units, terminate=terminate,
                              config=self.config.charms_config, local=True, release=self.config.charms_release,
                              repository=self.config.charms_repository)
        if same_environment and num_units:
            try:
                try:
                    juju.add_relation(environment, self.config.orchestra_service, self.config.transform_service,
                                      u'transform', u'transform')
                except RuntimeError as e:
                    raise NotImplementedError(to_bytes(u'Orchestra service must be available and running on default '
                                              'environment {0}, reason : {1}'.format(default, e)))
                try:
                    juju.add_relation(environment, self.config.storage_service, self.config.transform_service)
                except RuntimeError as e:
                    raise NotImplementedError(to_bytes(u'Storage service must be available and running on default '
                                              'environment {0}, reason : {1}'.format(default, e)))
            except NotImplementedError:
                juju.destroy_service(environment, self.config.transform_service)
                raise

    def get_transform_unit(self, environment, number):
        return juju.get_unit(environment, self.config.transform_service, number)

    def get_transform_units(self, environment):
        return juju.get_units(environment, self.config.transform_service)

    def get_transform_units_count(self, environment):
        return juju.get_units_count(environment, self.config.transform_service)

    def destroy_transform_unit(self, environment, number, terminate, test=False):
        if not test:
            raise NotImplementedError(u'This method is in development, set test to True to disable this warning.')
        juju.destroy_unit(environment, self.config.transform_service, number, terminate)

    # ------------------------------------------------------------------------------------------------------------------

    def get_transform_queues(self):
        return self.config.transform_queues

    def launch_transform_task(self, user_id, media_in_id, profile_id, filename, metadata, send_email, queue,
                              callback_url):
        user = self.get_user({u'_id': user_id}, {u'secret': 0})
        if not user:
            raise IndexError(to_bytes(u'No user with id {0}.'.format(user_id)))
        media_in = self.get_media({u'_id': media_in_id})
        if not media_in:  # FIXME maybe a media access control here
            raise IndexError(to_bytes(u'No media asset with id {0}.'.format(media_in_id)))
        profile = self.get_transform_profile({u'_id': profile_id})
        if not profile:  # FIXME maybe a profile access control here
            raise IndexError(to_bytes(u'No transformation profile with id {0}.'.format(profile_id)))
        if not queue in self.config.transform_queues:
            raise IndexError(to_bytes(u'No transformation queue with name {0}.'.format(queue)))
        media_out = Media(user_id=user_id, parent_id=media_in_id, filename=filename, metadata=metadata,
                          status=Media.PENDING)
        media_out.uri = self.config.storage_medias_uri(media_out)
        TransformTask.validate_task(media_in, profile, media_out)
        self.save_media(media_out)  # Save pending output media
        # FIXME create a one-time password to avoid fixed secret authentication ...
        callback = Callback(self.config.api_url + callback_url, u'node', self.config.node_secret)
        if self.is_mock:
            result_id = unicode(uuid.uuid4())
        else:
            result = TransformWorker.transform_task.apply_async(
                args=(object2json(media_in, False), object2json(media_out, False), object2json(profile, False),
                      object2json(callback, False)), queue=queue)
            result_id = result.id
        if not result_id:
            raise ValueError(to_bytes(u'Unable to transmit task to workers of queue {0}.'.format(queue)))
        logging.info(u'New transformation task {0} -> queue {1}.'.format(result_id, queue))
        task = TransformTask(user_id=user._id, media_in_id=media_in._id, media_out_id=media_out._id,
                             profile_id=profile._id, send_email=send_email, _id=result_id)
        task.add_statistic(u'add_date', datetime_now(), True)
        self._db.transform_tasks.save(task.__dict__, safe=True)
        return task

    def get_transform_task(self, spec, fields=None, load_fields=False, append_result=True):
        entity = self._db.transform_tasks.find_one(spec, fields)
        if not entity:
            return None
        task = dict2object(TransformTask, entity, inspect_constructor=True)
        if load_fields:
            task.load_fields(self.get_user({u'_id': task.user_id}, {u'secret': 0}),
                             self.get_media({u'_id': task.media_in_id}),
                             self.get_media({u'_id': task.media_out_id}),
                             self.get_transform_profile({u'_id': task.profile_id}))
        if append_result:
            task.append_async_result()
        return task

    def revoke_transform_task(self, task, terminate=False, remove=False, delete_media=False):
        u"""
        This do not delete tasks from tasks database (if remove=False) but set revoked attribute in tasks database and
        broadcast revoke request to transformation units with Celery. If the task is actually running it will be
        cancelled if terminated = True. The output media will be deleted if corresponding argument, delete_media = True.
        """
        # FIXME verify that no pending tasks needs the media that will be created by the task !
        if valid_uuid(task, none_allowed=False):
            task = self.get_transform_task({u'_id': task})
        task.is_valid(True)
        if task.status == TransformTask.CANCELED_STATUS:
            raise ValueError(to_bytes(u'Transformation task {0} is already revoked !'.format(task._id)))
        if task.status in TransformTask.FINAL_SATUS:
            raise ValueError(to_bytes(u'Cannot revoke a transformation task with status {0}.'.format(task.status)))
        task.status = TransformTask.REVOKED
        if self.is_mock:
            pass  # FIXME TODO
        else:
            revoke(task._id, terminate=terminate)
        self._db.transform_tasks.save(task.__dict__, safe=True)
        if delete_media and valid_uuid(task.media_out_id, none_allowed=False):
            self.delete_media(task.media_out_id)
        if remove:
            self._db.transform_tasks.remove({u'_id': task._id})

    def get_transform_tasks(self, spec=None, fields=None, skip=0, limit=0, sort=None, load_fields=False,
                            append_result=True):
        tasks, sort = [], sort or [('statistic.add_date', -1)]  # Sort by default, this is nicer like that !
        for entity in list(self._db.transform_tasks.find(spec=spec, fields=fields, skip=int(skip), limit=int(limit),
                                                         sort=sort, **self.db_find_options)):
            task = dict2object(TransformTask, entity, inspect_constructor=True)
            if load_fields:
                task.load_fields(self.get_user({u'_id': task.user_id}, {u'secret': 0}),
                                 self.get_media({u'_id': task.media_in_id}),
                                 self.get_media({u'_id': task.media_out_id}),
                                 self.get_transform_profile({u'_id': task.profile_id}))
            if append_result:
                task.append_async_result()
            tasks.append(task)
        return tasks
        # FIXME this is celery's way to do that:
        #for task in state.itertasks():
        #    print task
        #for entity in entities:
        #    task = get_transform_task_helper(entity._id)

    def get_transform_tasks_count(self, spec=None):
        return self._db.transform_tasks.find(spec, {u'_id': 1}).count()

    # ------------------------------------------------------------------------------------------------------------------

    def ensure_publisher_units(self, environment, num_units, terminate, test=False):
        u"""

        .. warning::

            FIXME implement more robust resources listing and removing, sometimes juju fail during a call
            (e.g. destroy_transform_units with num_units=10) and then some machines are not destroyed.

            * implement a garbage collector method callable by user when he want to destroy useless machines ?
            * implement a thread to handle removing unit asynchronously.
        """
        if not test:
            raise NotImplementedError(u'This method is in development, set test to True to disable this warning.')
        environments, default = self.get_environments()
        if environment == 'default':
            environment = default
        same_environment = (environment == default)
        config = juju.load_unit_config(self.config.publisher_config)
        config[u'rabbit_queues'] = u'publisher_{0}'.format(environment)
        if not same_environment:
            raise NotImplementedError(to_bytes(u'Unable to setup publication units into non-default environment {0} '
                                      '(default is {1}).'.format(environment, default)))
            config[u'mongo_connection'] = self.config.mongo_node_connection
            config[u'rabbit_connection'] = self.config.rabbit_connection
            # FIXME copy storage configuration, first method
            config[u'storage_address'] = self.config.storage_address
            config[u'storage_fstype'] = self.config.storage_fstype
            config[u'storage_mountpoint'] = self.config.storage_mountpoint
            config[u'storage_options'] = self.config.storage_options
        juju.save_unit_config(self.config.charms_config, self.config.publisher_service, config)
        juju.ensure_num_units(environment, self.config.publisher_service, num_units, terminate=terminate,
                              config=self.config.charms_config, local=True, release=self.config.charms_release,
                              repository=self.config.charms_repository)
        if same_environment and num_units:
            try:
                try:
                    juju.add_relation(environment, self.config.orchestra_service, self.config.publisher_service,
                                      u'publisher', u'publisher')
                except RuntimeError as e:
                    raise NotImplementedError(to_bytes(u'Orchestra service must be available and running on default '
                                              'environment {0}, reason : {1}'.format(default, e)))
                try:
                    juju.add_relation(environment, self.config.storage_service, self.config.publisher_service)
                except RuntimeError as e:
                    raise NotImplementedError(to_bytes(u'Storage service must be available and running on default '
                                              'environment {0}, reason : {1}'.format(default, e)))
            except NotImplementedError:
                juju.destroy_service(environment, self.config.publisher_service)
                raise

    def get_publisher_unit(self, environment, number):
        return juju.get_unit(environment, self.config.publisher_service, number)

    def get_publisher_units(self, environment):
        return juju.get_units(environment, self.config.publisher_service)

    def get_publisher_units_count(self, environment):
        return juju.get_units_count(environment, self.config.publisher_service)

    def destroy_publisher_unit(self, environment, number, terminate, test=False):
        if not test:
            raise NotImplementedError(u'This method is in development, set test to True to disable this warning.')
        juju.destroy_unit(environment, self.config.publisher_service, number, terminate)

    # ------------------------------------------------------------------------------------------------------------------

    def get_publisher_queues(self):
        return self.config.publisher_queues

    def launch_publisher_task(self, user_id, media_id, send_email, queue, callback_url):
        user = self.get_user({u'_id': user_id}, {u'secret': 0})
        if not user:
            raise IndexError(to_bytes(u'No user with id {0}.'.format(user_id)))
        media = self.get_media({u'_id': media_id})
        if not media:  # FIXME maybe a media access control here
            raise IndexError(to_bytes(u'No media asset with id {0}.'.format(media_id)))
        if not queue in self.config.publisher_queues:
            raise IndexError(to_bytes(u'No publication queue with name {0}.'.format(queue)))
        if media.status != Media.READY:
            raise NotImplementedError(to_bytes(u"Cannot launch the task, input media asset's status is {0}.".format(
                                      media.status)))
        if len(media.public_uris) > 0:
            raise NotImplementedError(to_bytes(u'Cannot launch the task, input media asset is already published.'))
        other = self.get_publisher_task({u'media_id': media._id})
        if other and other.status not in PublisherTask.FINAL_STATUS and other.status != PublisherTask.REVOKED:
            raise NotImplementedError(to_bytes(u'Cannot launch the task, input media asset will be published by another'
                                      ' task with id {0}.'.format(other._id)))
        # FIXME create a one-time password to avoid fixed secret authentication ...
        callback = Callback(self.config.api_url + callback_url, u'node', self.config.node_secret)
        if self.is_mock:
            result_id = unicode(uuid.uuid4())
        else:
            result = PublisherWorker.publisher_task.apply_async(
                args=(object2json(media, False), object2json(callback, False)), queue=queue)
            result_id = result.id
        if not result_id:
            raise ValueError(to_bytes(u'Unable to transmit task to workers of queue {0}.'.format(queue)))
        logging.info(u'New publication task {0} -> queue {1}.'.format(result_id, queue))
        task = PublisherTask(user_id=user._id, media_id=media._id, send_email=send_email, _id=result_id)
        task.add_statistic(u'add_date', datetime_now(), True)
        self._db.publisher_tasks.save(task.__dict__, safe=True)
        return task

    def get_publisher_task(self, spec, fields=None, load_fields=False, append_result=True):
        entity = self._db.publisher_tasks.find_one(spec, fields)
        if not entity:
            return None
        task = dict2object(PublisherTask, entity, inspect_constructor=True)
        if load_fields:
            task.load_fields(self.get_user({u'_id': task.user_id}, {u'secret': 0}),
                             self.get_media({u'_id': task.media_id}))
        if append_result:
            task.append_async_result()
        return task

    def update_publisher_task_and_media(self, task, publish_uri=None, revoke_task_id=None, status=None):
        if status:
            task.status = status
            media = self.get_media({u'_id': task.media_id})
            if not media:
                raise IndexError(to_bytes(u'Unable to find media asset with id {0}.'.format(task.media_id)))
            if task.status == PublisherTask.SUCCESS:
                task.publish_uri = publish_uri
                media.public_uris[task._id] = publish_uri
            elif task.status == PublisherTask.REVOKED:
                try:  # Remove if missing or not !
                    del media.public_uris[task._id]
                except:
                    pass
            elif task.status == PublisherTask.REVOKING:
                task.revoke_task_id = revoke_task_id
            self.save_media(media)  # FIXME do not save if not modified.
            self._db.publisher_tasks.save(task.__dict__, safe=True)  # FIXME The same here.
            return media
        return None

    def revoke_publisher_task(self, task, callback_url, terminate=False, remove=False):
        u"""
        This do not delete tasks from tasks database (if remove=False) but set revoked attribute in tasks database and
        broadcast revoke request to publication units with celery.
        If the task is actually running it will be cancelled if terminated = True.
        In any case, the output media asset will be deleted (task running or successfully finished).
        """
        if valid_uuid(task, none_allowed=False):
            task = self.get_publisher_task({u'_id': task})
        task.is_valid(True)
        if task.status in PublisherTask.CANCELED_STATUS:
            raise ValueError(to_bytes(u'Cannot revoke a publication task with status {0}.'.format(task.status)))
        if not self.is_mock:
            revoke(task._id, terminate=terminate)
        if task.status == PublisherTask.SUCCESS and not self.is_mock:
            # Send revoke task to the worker that published the media
            callback = Callback(self.config.api_url + callback_url, u'node', self.config.node_secret)
            queue = task.get_hostname()
            result = PublisherWorker.revoke_publisher_task.apply_async(
                args=(task.publish_uri, object2json(callback, False)), queue=queue)
            if not result.id:
                raise ValueError(to_bytes(u'Unable to transmit task to queue {0}.'.format(queue)))
            logging.info(u'New revoke publication task {0} -> queue {1}.'.format(result.id, queue))
            self.update_publisher_task_and_media(task, revoke_task_id=result.id, status=PublisherTask.REVOKING)
        else:
            self.update_publisher_task_and_media(task, status=PublisherTask.REVOKED)
        if remove:
            self._db.publisher_tasks.remove({u'_id': task._id})

    def get_publisher_tasks(self, spec=None, fields=None, skip=0, limit=0, sort=None, load_fields=False,
                            append_result=True):
        tasks, sort = [], sort or [('statistic.add_date', -1)]  # Sort by default, this is nicer like that !
        for entity in list(self._db.publisher_tasks.find(spec=spec, fields=fields, skip=int(skip), limit=int(limit),
                                                         sort=sort, **self.db_find_options)):
            task = dict2object(PublisherTask, entity, inspect_constructor=True)
            if load_fields:
                task.load_fields(self.get_user({u'_id': task.user_id}, {u'secret': 0}),
                                 self.get_media({u'_id': task.media_id}))
            if append_result:
                task.append_async_result()
            tasks.append(task)
        return tasks
        # FIXME this is celery's way to do that:
        #for task in state.itertasks():
        #    print task
        #for entity in entities:
        #    task = get_publisher_task_helper(entity._id)

    def get_publisher_tasks_count(self, spec=None):
        return self._db.publisher_tasks.find(spec, {u'_id': 1}).count()

    # ------------------------------------------------------------------------------------------------------------------

    def transform_callback(self, task_id, status):
        task = self.get_transform_task({u'_id': task_id})
        if not task:
            raise IndexError(to_bytes(u'No transformation task with id {0}.'.format(task_id)))
        media_out = self.get_media({u'_id': task.media_out_id})
        if not media_out:
            raise IndexError(to_bytes(u'Unable to find output media asset with id {0}.'.format(task.media_out_id)))
        if status == TransformTask.SUCCESS:
            media_out.status = Media.READY
            self.save_media(media_out)
            logging.info(u'{0} Media {1} is now {2}'.format(task_id, media_out.filename, media_out.status))
            #self.send_email_task(task, TransformTask.SUCCESS, media_out=media_out)
        else:
            self.delete_media(media_out)
            task.add_statistic(u'error_details', status.replace(u'\n', u'\\n'), True)
            self._db.transform_tasks.save(task.__dict__, safe=True)
            logging.info(u'{0} Error: {1}'.format(task_id, status))
            logging.info(u'{0} Media {1} is now deleted'.format(task_id, media_out.filename))
            #self.send_email_task(task, u'ERROR', media_out=media_out)

    def publisher_callback(self, task_id, publish_uri, status):
        task = self.get_publisher_task({u'_id': task_id})
        if not task:
            raise IndexError(to_bytes(u'No publication task with id {0}.'.format(task_id)))
        if status == PublisherTask.SUCCESS:
            media = self.update_publisher_task_and_media(task, publish_uri=publish_uri, status=status)
            logging.info(u'{0} Media {1} is now available at {2}'.format(task_id, media.filename, media.public_uris))
            #self.send_email_task(task, PublisherTask.SUCCESS, media=media)
        else:
            task.add_statistic(u'error_details', status.replace(u'\n', u'\\n'), True)
            self._db.publisher_tasks.save(task.__dict__, safe=True)
            logging.info(u'{0} Error: {1}'.format(task_id, status))
            logging.info(u'{0} Media {1} is not modified'.format(task_id, media.filename))
            #self.send_email_task(task, u'ERROR', media=None)

    def publisher_revoke_callback(self, task_id, publish_uri, status):
        task = self.get_publisher_task({u'revoke_task_id': task_id})
        if not task:
            raise IndexError(to_bytes(u'No publication task with revoke_task_id {0}.'.format(task_id)))
        if status == PublisherTask.SUCCESS:
            media = self.update_publisher_task_and_media(task, status=PublisherTask.REVOKED)
            logging.info(u'{0} Media {1} is now available at {2}'.format(task_id, media.filename, media.public_uris))
        else:
            task.add_statistic('revoke_error_details', status.replace(u'\n', u'\\n'), True)
            self._db.publisher_tasks.save(task.__dict__, safe=True)
            logging.info(u'{0} Error: {1}'.format(task_id, status))
            logging.info(u'{0} Media {1} is not modified'.format(task_id, media.filename))


# ----------------------------------------------------------------------------------------------------------------------

def get_test_api_core():
    orchestra = OrchestraAPICore(ORCHESTRA_CONFIG_TEST)
    init_api(orchestra, u'../../scenarios/current')
    print(u'There are {0} registered users.'.format(len(orchestra.get_users())))
    print(u'There are {0} available media assets.'.format(len(orchestra.get_medias())))
    print(u'There are {0} available transformation profiles.'.format(len(orchestra.get_transform_profiles())))
    print(u'There are {0} launched transformation tasks.'.format(len(orchestra.get_transform_tasks())))
    return orchestra


def init_api(api_core_or_client, api_init_csv_directory, flush=False, add_users=True, add_profiles=True,
             add_medias=True, add_tasks=True):

    is_core = isinstance(api_core_or_client, OrchestraAPICore)
    orchestra = api_core_or_client if is_core else None
    api_client = api_core_or_client if not is_core else None

    if flush:
        if is_core:
            orchestra.flush_db()
            # FIXME remove media files
        else:
            api_client.flush()
            api_client.remove_medias()

    users, reader = [], csv_reader(os.path.join(api_init_csv_directory, u'users.csv'))
    for first_name, last_name, email, secret, admin_platform in reader:
        user = User(first_name, last_name, email, secret, admin_platform)
        users.append(user)
        if not add_users:
            continue
        print(u'Adding user {0}'.format(user.name))
        if is_core:
            orchestra.save_user(user, hash_secret=True)
        else:
            api_client.users.add(user)
    users = orchestra.get_users() if is_core else users# api_client.users.list()

    if add_profiles:
        i, reader = 0, csv_reader(os.path.join(api_init_csv_directory, u'tprofiles.csv'))
        for title, description, encoder_name, encoder_string in reader:
            user = users[i]
            profile = TransformProfile(title=title, description=description, encoder_name=encoder_name,
                                       encoder_string=encoder_string)
            print(u'Adding transformation profile {0} as user {1}'.format(profile.title, user.name))
            if is_core:
                orchestra.save_transform_profile(profile)
            else:
                api_client.auth = user
                api_client.transform_profiles.add(profile)
            i = (i + 1) % len(users)

    if add_medias:
        i, reader = 0, csv_reader(os.path.join(api_init_csv_directory, u'medias.csv'))
        for local_filename, filename, title in reader:
            user = users[i]
            print(os.getcwd())
            media = Media(user_id=user._id, filename=filename, metadata={u'title': title})
            if not os.path.exists(local_filename):
                print(u'Skip media asset {0}, file "{1}" Not found.'.format(media.metadata[u'title'], local_filename))
                continue
            print(u'Adding media asset {0} as user {1}'.format(media.metadata[u'title'], user.name))
            if is_core:
                #orchestra.config. bla bla -> get media.uri
                orchestra.save_media(media)
            else:
                api_client.auth = user
                media.uri = api_client.upload_media(local_filename)
                api_client.medias.add(media)
            i = (i + 1) % len(users)

    if not is_core:
        return

    if add_tasks:
        reader = csv_reader(os.path.join(api_init_csv_directory, u'ttasks.csv'))
        for user_email, in_filename, profile_title, out_filename, out_title, send_email, queue in reader:
            user = orchestra.get_user({u'mail': user_email})
            if not user:
                raise IndexError(to_bytes(u'No user with e-mail address {0}.'.format(user_email)))
            media_in = orchestra.get_media({u'filename': in_filename})
            if not media_in:
                raise IndexError(to_bytes(u'No media asset with filename {0}.'.format(in_filename)))
            profile = orchestra.get_transform_profile({u'title': profile_title})
            if not profile:
                raise IndexError(to_bytes(u'No transformation profile with title {0}.'.format(profile_title)))
            print(u'Launching transformation task {0} with profile {1} as user {2}.'.format(
                  media_in.metadata[u'title'], profile.title, user.name))
            metadata = {u'title': out_title}
            orchestra.launch_transform_task(user._id, media_in._id, profile._id, out_filename, metadata, send_email,
                                            queue, u'/transform/callback')


# Main -----------------------------------------------------------------------------------------------------------------

if __name__ == u'__main__':
    from .pytoolbox.encoding import configure_unicode
    configure_unicode()
    get_test_api_core()