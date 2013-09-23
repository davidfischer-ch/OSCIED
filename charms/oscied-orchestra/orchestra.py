#!/usr/bin/env python
# -*- coding: utf-8 -*-

#**********************************************************************************************************************#
#              OPEN-SOURCE CLOUD INFRASTRUCTURE FOR ENCODING AND DISTRIBUTION : ORCHESTRA
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

# FIXME mongo concurrency : http://emptysquare.net/blog/requests-in-python-and-mongodb/

import logging
import sys
from flask import Flask, abort, request
from kitchen.text.converters import to_bytes
from library.oscied_lib.pyutils.py_flask import check_id, get_request_data, json_response, map_exceptions
from library.oscied_lib.pyutils.py_logging import setup_logging
from library.oscied_lib.pyutils.py_serialization import object2json
from library.oscied_lib.oscied_api import OrchestraAPICore
from library.oscied_lib.oscied_config import OrchestraLocalConfig
from library.oscied_lib.oscied_models import Media, User, TransformProfile


# Global variables -----------------------------------------------------------------------------------------------------

app = Flask(__name__)


# ----------------------------------------------------------------------------------------------------------------------
# http://publish.luisrei.com/articles/flaskrest.html

def requires_auth(request, allow_root=False, allow_node=False, allow_any=False, role=None, id=None, mail=None):
    """
    This method implements Orchestra's RESTful API authentication logic. Here is ensured that an access to a method of
    the API is filtered based on rules (this method's parameters). HTTP user agent must authenticate through HTTP basic
    access authentication. The username must be user's email address and password must be user's secret. This not apply
    for system-users like root or node as they do not have any e-mail address.

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
        @app.route(u'/my/example/route', methods=[u'GET'])
        def api_my_example_route():
            if request.method == u'GET':
                auth_user = requires_auth(request=request, allow_any=True)
                ...
                return ok_200(u'my return value', True)

        # Allow root system-user or any user with admin attribute set
        @app.route(u'/my/restricted/route', methods=[u'GET'])
        def api_my_restricted_route():
            if request.method == u'GET':
                auth_user = requires_auth(request=request, allow_root=True, allow_role='admin')
                ...
                return ok_200(u'my return value', True)
    """
    auth = request.authorization
    if not auth or auth.username is None or auth.password is None:
        abort(401, u'Authenticate.')  # Testing for None is maybe too much ... Security is like that
    username = auth.username
    password = auth.password
    root = (username == u'root' and password == orchestra.config.root_secret)
    node = (username == u'node' and password == orchestra.config.node_secret)
    user = None
    if not root and not node:
        user = orchestra.get_user({u'mail': username}, secret=password)
        username = user.name if user else None
    if not root and not user and not node:
        abort(401, u'Authentication Failed.')
    if root and allow_root:
        logging.info(u'Allowed authenticated root')
        return orchestra.root_user
    if node and allow_node:
        logging.info(u'Allowed authenticated worker/node')
        return orchestra.node_user
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


# Utilities ------------------------------------------------------------------------------------------------------------

@app.errorhandler(400)
def error_400(value=None):
    return json_response(400, value=value, include_properties=False)


@app.errorhandler(401)
def error_401(value=None):
    return json_response(401, value=value, include_properties=False)


@app.errorhandler(403)
def error_403(value=None):
    return json_response(403, value=value, include_properties=False)


@app.errorhandler(404)
def error_404(value=None):
    return json_response(404, value=value, include_properties=False)


@app.errorhandler(415)
def error_415(value=None):
    return json_response(415, value=value, include_properties=False)


@app.errorhandler(500)
def error_500(value=None):
    return json_response(500, value=value, include_properties=False)


@app.errorhandler(501)
def error_501(value=None):
    return json_response(501, value=value, include_properties=False)


def ok_200(value, include_properties):
    return json_response(200, value=value, include_properties=include_properties)


# Index ----------------------------------------------------------------------------------------------------------------

@app.route(u'/', methods=[u'GET'])
@app.route(u'/index', methods=[u'GET'])
def api_root():
    """
    Return an about string.

    This method is actually used by Orchestra charm's hooks to check API's status.

    **Example request**:

    .. sourcecode:: http

        GET / HTTP/1.1
        Host: example.com
        Accept: application/json

    **Example response**:

    .. sourcecode:: http

        HTTP/1.1 200 OK
        Vary: Accept
        Content-Type: application/json

        {
          "status": 200, "value":
          "Orchestra : EBU's OSCIED Orchestrator by David Fischer 2012-2013\\n"
        }

    :Allowed: Any user (including unauthenticated)
    :statuscode 200: OK
    """
    try:
        return ok_200(orchestra.about, False)
    except Exception as e:
        map_exceptions(e)


# System management ----------------------------------------------------------------------------------------------------

@app.route(u'/flush', methods=[u'POST'])
def api_flush():
    """
    Flush Orchestrator's database.

    This method is useful for testing/development purposes.

    **Example request**:

    .. sourcecode:: http

        POST /flush HTTP/1.1
        Host: example.com
        Header: root:password
        Accept: application/json

    **Example response**:

    .. sourcecode:: http

        HTTP/1.1 200 OK
        Vary: Accept
        Content-Type: application/json

        {"status": 200, "value": "Orchestra database flushed !"}

    :Allowed: Only root
    :statuscode 200: OK
    :statuscode 401: Authenticate.
    :statuscode 403: Authentication Failed.
    """
    try:
        requires_auth(request=request, allow_root=True)
        orchestra.flush_db()
        return ok_200(u'Orchestra database flushed !', False)
    except Exception as e:
        map_exceptions(e)


# Users management -----------------------------------------------------------------------------------------------------

@app.route(u'/user/login', methods=[u'GET'])
def api_user_login():
    """
    Return authenticated user serialized to JSON if authentication passed (without ``secret`` field).

    This method is useful for WebUI to simulate stateful login scheme and get informations about the user.

    .. note::

        This is kind of duplicate with API's GET /user/id/`id` method ...

    **Example request**:

    .. sourcecode:: http

        GET /user/login HTTP/1.1
        Host: somewhere.com
        Header: tabby@bernex.ch:miaow
        Accept: application/json

    **Example response**:

    .. sourcecode:: http

        HTTP/1.1 200 OK
        Vary: Accept
        Content-Type: application/json

        {
          "status": 200,
          "value": {
            "_id": "c4daa8a6-6be4-11e2-ae91-3085a9accb47",
            "first_name": "Tabby",
            "last_name": "Fischer",
            "name": "Tabby Fischer",
            "mail": "tabby@bernex.ch",
            "admin_platform": false
          }
        }

    :Allowed: Any user
    :statuscode 200: OK
    :statuscode 401: Authenticate.
    :statuscode 403: Authentication Failed.
    """
    try:
        auth_user = requires_auth(request=request, allow_any=True)
        delattr(auth_user, u'secret')  # do not send back user's secret
        return ok_200(auth_user, True)
    except Exception as e:
        map_exceptions(e)


@app.route(u'/user/count', methods=[u'GET'])
def api_user_count():
    """
    Return the number of users.

    **Example request**:

    .. sourcecode:: http

        GET /user/count HTTP/1.1
        Host: somewhere.com
        Header: bram@oscied.org:oscied
        Accept: application/json

    **Example response**:

    .. sourcecode:: http

        HTTP/1.1 200 OK
        Vary: Accept
        Content-Type: application/json

        {"status": 200, "value": 5000}

    :Allowed: Root and any user
    :statuscode 200: OK
    :statuscode 401: Authenticate.
    :statuscode 403: Authentication Failed.
    """
    try:
        requires_auth(request=request, allow_root=True, allow_any=True)
        data = get_request_data(request, accepted_keys=orchestra.db_count_keys, qs_only_first_value=True, fail=False)
        return ok_200(orchestra.get_users_count(**data), False)
    except Exception as e:
        map_exceptions(e)


@app.route(u'/user', methods=[u'GET'])
def api_user_get():
    """
    Return an array containing the users serialized to JSON (without ``secret`` fields).

    **Example request**:

    .. sourcecode:: http

        GET /user HTTP/1.1
        Host: somewhere.com
        Header: peter@oscied.org:oscied
        Accept: application/json

    **Example response**:

    .. sourcecode:: http

        HTTP/1.1 200 OK
        Vary: Accept
        Content-Type: application/json

        {
          "status": 200,
          "value": [{"_id": "...", "...": "..."}, {"_id": "..."}]
        }

    :Allowed: Root and user with admin_platform attribute set
    :statuscode 200: OK
    :statuscode 401: Authenticate.
    :statuscode 403: Authentication Failed.
    """
    try:
        requires_auth(request=request, allow_root=True, role=u'admin_platform')
        data = get_request_data(request, accepted_keys=orchestra.db_find_keys, qs_only_first_value=True, fail=False)
        return ok_200(orchestra.get_users(**data), True)
    except Exception as e:
        map_exceptions(e)


@app.route(u'/user', methods=[u'POST'])
def api_user_post():
    """
    Add a user.

    **Example request**:

    .. sourcecode:: http

        POST /user HTTP/1.1
        Host: somewhere.com
        Header: kouadi@oscied.org:oscied
        Accept: application/json
        Content-Type: application/json

        {
          "first_name": "Laurent",
          "last_name": "Nicolet",
          "mail": "laurent@comique.ch",
          "secret": "genevois_style",
          "admin_platform": false
        }

    **Example response**:

    .. sourcecode:: http

        HTTP/1.1 200 OK
        Vary: Accept
        Content-Type: application/json

        {
          "status": 200,
          "value": {
            "_id": "8bda488c-6be8-11e2-89b7-3085a9accb47",
            "first_name": "Laurent",
            "last_name": "Nicolet",
            "name": "Laurent Nicolet",
            "mail": "laurent@comique.ch",
            "admin_platform": false
          }
        }

    :Allowed: Root and user with admin_platform attribute set
    :query first_name: New user's first name (required)
    :query last_name: New user's last name (required)
    :query mail: New user's email address (required)
    :query secret: New user's secret (required)
    :query admin_platform: New user's admin_platform (required)
    :statuscode 200: OK
    :statuscode 400: on type or value error
    :statuscode 400: Key ``key`` not found.
    :statuscode 400: The email address ``mail`` is already used by another user.
    :statuscode 401: Authenticate.
    :statuscode 403: Authentication Failed.
    :statuscode 415: Requires (valid) json content-type.
    """
    try:
        requires_auth(request=request, allow_root=True, role=u'admin_platform')
        data = get_request_data(request, qs_only_first_value=True)
        user = User(first_name=data[u'first_name'], last_name=data[u'last_name'], mail=data[u'mail'],
                    secret=data[u'secret'], admin_platform=data[u'admin_platform'])
        orchestra.save_user(user, hash_secret=True)
        delattr(user, u'secret')  # do not send back user's secret
        return ok_200(user, True)
    except Exception as e:
        map_exceptions(e)


@app.route(u'/user/id/<id>', methods=[u'GET'])
def api_user_id_get(id):
    """
    Return a user serialized to JSON (without ``secret`` field).

    **Example request**:

    .. sourcecode:: http

        GET /user/id/c4daa8a6-6be4-11e2-ae91-3085a9accb47 HTTP/1.1
        Host: somewhere.com
        Header: michael@oscied.org:oscied
        Accept: application/json

    **Example response**:

    .. sourcecode:: http

        HTTP/1.1 200 OK
        Vary: Accept
        Content-Type: application/json

        {
          "status": 200,
          "value": {
            "_id": "c4daa8a6-6be4-11e2-ae91-3085a9accb47",
            "first_name": "Tabby",
            "last_name": "Fischer",
            "name": "Tabby Fischer",
            "mail": "tabby@bernex.ch",
            "admin_platform": false
          }
        }

    :Allowed: Root and any user
    :param id: id of user to get
    :statuscode 200: OK
    :statuscode 401: Authenticate.
    :statuscode 403: Authentication Failed.
    :statuscode 404: No user with id ``id``.
    :statuscode 415: Wrong id format ``id``.
    """
    try:
        check_id(id)
        requires_auth(request=request, allow_root=True, allow_any=True)
        user = orchestra.get_user(spec={u'_id': id}, fields={u'secret': 0})
        if not user:
            raise IndexError(to_bytes(u'No user with id {0}.'.format(id)))
        return ok_200(user, True)
    except Exception as e:
        map_exceptions(e)


@app.route(u'/user/id/<id>', methods=[u'PATCH', u'PUT'])
def api_user_id_patch(id):
    """
    Update an user.

    User's admin_platform attribute can only be modified by root or any authenticated user with admin_platform attribute
    set.

    **Example request**:

    .. sourcecode:: http

        PUT /user/id/8bda488c-6be8-11e2-89b7-3085a9accb47 HTTP/1.1
        Host: somewhere.com
        Header: loic@oscied.org:oscied
        Accept: application/json
        Content-Type: application/json

        {
          "mail": "laurent.nicolet@comiques.ch",
          "secret": "gnevois_style",
          "admin_platform": true
        }

    **Example response**:

    .. sourcecode:: http

        HTTP/1.1 200 OK
        Vary: Accept
        Content-Type: application/json

        {
          "status": 200,
          "value": "The user \\"Laurent Nicolet\\" has been updated."
        }

    :Allowed: Root, user with admin_platform attribute set or the user itself
    :param id: id of user to get
    :query first_name: User's first name (optional)
    :query last_name: User's last name (optional)
    :query mail: User's email address (optional)
    :query secret: User's secret (optional)
    :query admin_platform: User's admin_platform (optional)
    :statuscode 200: OK
    :statuscode 400: on type or value error
    :statuscode 400: Key ``key`` not found.
    :statuscode 400: The email address ``mail`` is already used by another user.
    :statuscode 401: Authenticate.
    :statuscode 403: Authentication Failed.
    :statuscode 404: No user with id ``id``
    :statuscode 415: Wrong id format ``id``.
    :statuscode 415: Requires (valid) json content-type.
    """
    try:
        check_id(id)
        auth_user = requires_auth(request=request, allow_root=True, role=u'admin_platform', id=id)
        user = orchestra.get_user(spec={u'_id': id})
        data = get_request_data(request, qs_only_first_value=True)
        if not user:
            raise IndexError(to_bytes(u'No user with id {0}.'.format(id)))
        old_name = user.name
        if u'first_name' in data:
            user.first_name = data[u'first_name']
        if u'last_name' in data:
            user.last_name = data[u'last_name']
        if u'mail' in data:
            user.mail = data[u'mail']
        if u'secret' in data:
            user.secret = data[u'secret']
        if auth_user.admin_platform and u'admin_platform' in data:
            user.admin_platform = data[u'admin_platform']
        orchestra.save_user(user, hash_secret=True)
        return ok_200(u'The user "{0}" has been updated.'.format(old_name), False)
    except Exception as e:
        map_exceptions(e)


@app.route(u'/user/id/<id>', methods=[u'DELETE'])
def api_user_id_delete(id):
    """
    Delete a user.

    **Example request**:

    .. sourcecode:: http

        DELETE /user/id/8bda488c-6be8-11e2-89b7-3085a9accb47 HTTP/1.1
        Host: somewhere.com
        Header: laurent.nicolet@comiques.ch:gnevois_style
        Accept: application/json

    **Example response**:

    .. sourcecode:: http

        HTTP/1.1 200 OK
        Vary: Accept
        Content-Type: application/json

        {
          "status": 200,
          "value": "The user \\"Laurent Nicolet\\" has been deleted."
        }

    :Allowed: Root, user with admin_platform attribute set or the user itself
    :param id: id of user to delete
    :statuscode 200: OK
    :statuscode 401: Authenticate.
    :statuscode 403: Authentication Failed.
    :statuscode 404: No user with id ``id``.
    :statuscode 415: Wrong id format ``id``.
    """
    try:
        check_id(id)
        requires_auth(request=request, allow_root=True, role=u'admin_platform', id=id)
        user = orchestra.get_user(spec={u'_id': id})
        if not user:
            raise IndexError(to_bytes(u'No user with id {0}.'.format(id)))
        orchestra.delete_user(user)
        return ok_200(u'The user "{0}" has been deleted.'.format(user.name), False)
    except Exception as e:
        map_exceptions(e)


# Medias management ----------------------------------------------------------------------------------------------------

@app.route(u'/media/count', methods=[u'GET'])
def api_media_count():
    """
    Return the number of media assets.

    **Example request**:

    .. sourcecode:: http

        GET /media/count HTTP/1.1
        Host: somewhere.com
        Header: tewfiq@oscied.org:oscied
        Accept: application/json

    **Example response**:

    .. sourcecode:: http

        HTTP/1.1 200 OK
        Vary: Accept
        Content-Type: application/json

        {"status": 200, "value": 8000}

    :Allowed: Any user
    :statuscode 200: OK
    :statuscode 401: Authenticate.
    :statuscode 403: Authentication Failed.
    """
    try:
        requires_auth(request=request, allow_any=True)
        data = get_request_data(request, accepted_keys=orchestra.db_count_keys, qs_only_first_value=True, fail=False)
        return ok_200(orchestra.get_medias_count(**data), False)
    except Exception as e:
        map_exceptions(e)


@app.route(u'/media/HEAD', methods=[u'GET'])
def api_media_head():
    """
    Return an array containing the informations about the media assets serialized to JSON.

    **Example request**:

    .. sourcecode:: http

        GET /media/HEAD HTTP/1.1
        Host: somewhere.com
        Header: andres@oscied.org:oscied
        Accept: application/json

    **Example response**:

    .. sourcecode:: http

        HTTP/1.1 200 OK
        Vary: Accept
        Content-Type: application/json

        {
          "status": 200,
          "value": [{"_id": "...", "...": "..."}, {"_id": "..."}]
        }

    :Allowed: Any user
    :statuscode 200: OK
    :statuscode 401: Authenticate.
    :statuscode 403: Authentication Failed.
    """
    try:
        requires_auth(request=request, allow_any=True)
        data = get_request_data(request, accepted_keys=orchestra.db_find_keys, qs_only_first_value=True, fail=False)
        return ok_200(orchestra.get_medias(**data), True)
    except Exception as e:
        map_exceptions(e)


@app.route(u'/media', methods=[u'GET'])
def api_media_get():
    """
    Return an array containing the informations about the media assets serialized to JSON.

    All ``thing_id`` fields are replaced by corresponding ``thing``.
    For example ``user_id`` is replaced by ``user``'s data.

    **Example request**:

    .. sourcecode:: http

        GET /media HTTP/1.1
        Host: somewhere.com
        Header: nabil@oscied.org:oscied
        Accept: application/json

    **Example response**:

    .. sourcecode:: http

        HTTP/1.1 200 OK
        Vary: Accept
        Content-Type: application/json

        {
          "status": 200,
          "value": [{"_id": "...", "...": "..."}, {"_id": "..."}]
        }

    :Allowed: Any user
    :statuscode 200: OK
    :statuscode 401: Authenticate.
    :statuscode 403: Authentication Failed.
    """
    try:
        requires_auth(request=request, allow_any=True)
        data = get_request_data(request, accepted_keys=orchestra.db_find_keys, qs_only_first_value=True, fail=False)
        return ok_200(orchestra.get_medias(load_fields=True, **data), True)
    except Exception as e:
        map_exceptions(e)


@app.route(u'/media', methods=[u'POST'])
def api_media_post():
    """
    Register a media asset and add informations about it.

    This method only register already uploaded media asset to the shared storage.
    For example, the WebUI will upload a media asset to uploads path **before** registering it with this method.

    Medias in the shared storage are renamed with the following convention:
        ``storage_root``/medias/``user_id``/``media_id``

    When published or downloaded, media asset file-name will be ``filename``.
    Spaces ( ) are not allowed and they will be converted to underscores (_).

    Media asset's ``metadata`` must contain any valid JSON string. Only the ``title`` key is required.
    The orchestrator will automatically add ``add_date`` and ``duration`` to ``metadata``.

    .. note::

        Registration of external media assets (aka. http://) will be an interesting improvement.

    **Example request**:

    .. sourcecode:: http

        POST /media HTTP/1.1
        Host: somewhere.com
        Header: d@f.com:oscied
        Accept: application/json
        Content-Type: application/json

        {
          "uri": "glusterfs://<address>/medias_volume/uploads/
                  Project London - Official Trailer [2009].mp4",
          "filename": "Project_London_trailer_2009.mp4",
          "metadata":
          {
            "title": "Project London - Official Trailer (2009)"
          }
        }

    **Example response**:

    .. sourcecode:: http

        HTTP/1.1 200 OK
        Vary: Accept
        Content-Type: application/json

        {
          "status": 200,
          "value": {
            "_id": "96590fdc-74f8-11e2-8c58-3085a9acc651",
            "user_id": "1298f206-74f8-11e2-9b82-3085a9acc11b",
            "parent_id": null,
            "uri": "glusterfs://<address>/medias_volume/medias/
                    <user_id>/<media_id>",
            "public_uris": null,
            "filename": "Project_London_trailer_2009.mp4",
            "metadata": {
              "add_date": "2013-02-02 14:05",
              "duration": "00:02:44.88", "size": 54871886,
              "title": "Project London - Official Trailer (2009)"
            },
            "status": "READY"
          }
        }

    :Allowed: Any user can do that
    :query uri: Media asset's (source) URI, actually only shared storage's URI are handled (required)
    :query filename: Media's filename when downloaded or published (required)
    :query metadata: JSON string containing metadatas about the media asset (required)
    :statuscode 200: OK
    :statuscode 400: on type or value error
    :statuscode 400: Key ``key`` not found.
    :statuscode 400: The media URI ``uri`` is already used by another media asset.
    :statuscode 400: Title key is required in media asset's metadata.
    :statuscode 401: Authenticate.
    :statuscode 403: Authentication Failed.
    :statuscode 404: An error occured : ``OSError``
    :statuscode 415: Requires (valid) json content-type.
    :statuscode 501: FIXME Add of external URI not implemented.
    """
    try:
        auth_user = requires_auth(request=request, allow_any=True)
        data = get_request_data(request, qs_only_first_value=True)
        media = Media(user_id=auth_user._id, uri=data[u'uri'], filename=data[u'filename'], metadata=data[u'metadata'],
                      status=Media.READY)
        orchestra.save_media(media)
        return ok_200(media, True)
    except Exception as e:
        map_exceptions(e)


# FIXME why HEAD verb doesn't work (curl: (18) transfer closed with 263 bytes remaining to read) ?
@app.route(u'/media/id/<id>/HEAD', methods=[u'GET'])
def api_media_id_head(id):
    """
    Return the informations about a media asset serialized to JSON.

    **Example request**:

    .. sourcecode:: http

        GET /media/id/96590fdc-74f8-11e2-8c58-3085a9acc651/HEAD HTTP/1.1
        Host: somewhere.com
        Header: monique@oscied.org:oscied
        Accept: application/json

    **Example response**:

    .. sourcecode:: http

        HTTP/1.1 200 OK
        Vary: Accept
        Content-Type: application/json

        {
          "status": 200,
          "value": {
            "_id": "b8b9ae78-74f8-11e2-8dae-3085a9accbc1",
            "user_id": "4e8ec55e-74f7-11e2-8451-3085a9acc8e0b",
            "parent_id": null,
            "uri": "glusterfs://<address>/medias_volume/medias/
                    <user_id>/<media_id>",
            "public_uris": null,
            "filename": "Psy_gangnam_style.flv",
            "metadata": {
              "duration": "00:04:12.16",
              "add_date": "2013-02-11 22:37",
              "title": "Psy - Gangnam Style",
              "size": 183190475
            },
            "status": "READY"
          }
        }

    :Allowed: Any user
    :param id: id of media asset to get
    :statuscode 200: OK
    :statuscode 401: Authenticate.
    :statuscode 403: Authentication Failed.
    :statuscode 404: No media asset with id ``id``.
    :statuscode 415: Wrong id format ``id``.
    """
    try:
        check_id(id)
        requires_auth(request=request, allow_any=True)
        media = orchestra.get_media(spec={u'_id': id})
        if not media:
            raise IndexError(to_bytes(u'No media asset with id {0}.'.format(id)))
        return ok_200(media, True)
    except Exception as e:
        map_exceptions(e)


@app.route(u'/media/id/<id>', methods=[u'GET'])
def api_media_id_get(id):
    """
    Return the informations about a media asset serialized to JSON.

    All ``thing_id`` fields are replaced by corresponding ``thing``.
    For example ``user_id`` is replaced by ``user``'s data.

    **Example request**:

    .. sourcecode:: http

        GET /media/id/96590fdc-74f8-11e2-8c58-3085a9acc651 HTTP/1.1
        Host: somewhere.com
        Header: estelle@oscied.org:oscied
        Accept: application/json

    **Example response**:

    .. sourcecode:: http

        HTTP/1.1 200 OK
        Vary: Accept
        Content-Type: application/json

        {
          "status": 200,
          "value": {
            "_id": "b8b9ae78-74f8-11e2-8dae-3085a9accbc1",
            "user": {
            "_id": "4e8ec55e-74f7-11e2-8451-3085a9acc8e0b",
              "first_name": "David",
              "last_name": "Fischer",
              "name": "David Fischer",
              "mail": "d@f.com",
              "admin_platform": true
            },
            "parent": null,
            "uri": "glusterfs://<address>/medias_volume/medias/
                    <user_id>/<media_id>",
            "public_uris": null,
            "filename": "Psy_gangnam_style.flv",
            "metadata": {
              "duration": "00:04:12.16",
              "add_date": "2013-02-11 22:37",
              "title": "Psy - Gangnam Style",
              "size": 183190475
            },
            "status": "READY"
          }
        }

    :Allowed: Any user
    :param id: id of media asset to get
    :statuscode 200: OK
    :statuscode 401: Authenticate.
    :statuscode 403: Authentication Failed.
    :statuscode 404: No media asset with id ``id``.
    :statuscode 415: Wrong id format ``id``.
    :statuscode 415: Requires json content-type.
    """
    try:
        check_id(id)
        requires_auth(request=request, allow_any=True)
        media = orchestra.get_media(spec={'_id': id}, load_fields=True)
        if not media:
            raise IndexError(to_bytes(u'No media asset with id {0}.'.format(id)))
        return ok_200(media, True)
    except Exception as e:
        map_exceptions(e)


@app.route(u'/media/id/<id>', methods=[u'PATCH', u'PUT'])
def api_media_id_patch(id):
    """
    Update the informations of a media asset (only metadata field can be updated).

   **Example request**:

    .. sourcecode:: http

        PUT /media/id/a396fe66-74ee-11e2-89ad-3085a9accbb8 HTTP/1.1
        Host: somewhere.com
        Header: anthony@oscied.org:oscied
        Accept: application/json
        Content-Type: application/json

        {"filename": "the_fifth_element.mp4"}

    **Example response**:

    .. sourcecode:: http

        HTTP/1.1 200 OK
        Vary: Accept
        Content-Type: application/json

        {
          "status": 200,
          "value": "The media asset \\"fifth_element.mp4\\" has been updated."
        }

    :Allowed: Only the author of the media
    :param id: media's id
    :query filename: Media's filename when downloaded or published (optional)
    :query metadata: JSON string containing metadatas about the media asset (optional)
    :statuscode 200: OK
    :statuscode 400: Key ``key`` not found. *or* on type or value error
    :statuscode 401: Authenticate.
    :statuscode 403: Authentication Failed.
    :statuscode 403: You are not allowed to modify media asset with id ``id``.
    :statuscode 404: No media asset with id ``id``.
    :statuscode 415: Wrong id format ``id``.
    :statuscode 415: Requires (valid) json content-type.
    """
    try:
        check_id(id)
        auth_user = requires_auth(request=request, allow_any=True)
        media = orchestra.get_media(spec={u'_id': id})
        data = get_request_data(request, qs_only_first_value=True)
        if not media:
            raise IndexError(to_bytes(u'No media asset with id {0}.'.format(id)))
        if auth_user._id != media.user_id:
            abort(403, u'You are not allowed to modify media asset with id {0}.'.format(id))
        if u'metadata' in data:
            media.metadata = data[u'metadata']
        orchestra.save_media(media)
        return ok_200(u'The media asset "{0}" has been updated.'.format(media.filename), False)
    except Exception as e:
        map_exceptions(e)


@app.route(u'/media/id/<id>', methods=[u'DELETE'])
def api_media_id_delete(id):
    """
    Remove a media asset from the shared storage and update informations about it (set status to DELETED).

   **Example request**:

    .. sourcecode:: http

        DELETE /media/id/a396fe66-74ee-11e2-89ad-3085a9accbb8 HTTP/1.1
        Host: somewhere.com
        Header: sandro@oscied.org:oscied
        Accept: application/json

    **Example response**:

    .. sourcecode:: http

        HTTP/1.1 200 OK
        Vary: Accept
        Content-Type: application/json

        {
          "status": 200,
          "value": "The media asset \\"fifth_element.mp4\\" has been deleted."
        }

    :Allowed: Only the author of the media
    :param id: id of media asset to delete
    :statuscode 200: OK
    :statuscode 400: Cannot delete the media, it is actually in use by transformation task with id ``id`` and status ``status``.
    :statuscode 400: Cannot delete the media, it is actually in use by publication task with id ``id`` and status ``status``.
    :statuscode 401: Authenticate.
    :statuscode 403: Authentication Failed.
    :statuscode 403: You are not allowed to delete media asset with id ``id``.
    :statuscode 404: No media asset with id ``id``.
    :statuscode 415: Wrong id format ``id``.
    :statuscode 501: FIXME Delete of external URI not implemented.
    """
    try:
        check_id(id)
        auth_user = requires_auth(request=request, allow_any=True)
        media = orchestra.get_media(spec={u'_id': id})
        if not media:
            raise IndexError(to_bytes(u'No media asset with id {0}.'.format(id)))
        if auth_user._id != media.user_id:
            abort(403, u'You are not allowed to delete media asset with id {0}.'.format(id))
        orchestra.delete_media(media)
        return ok_200(u'The media asset "{0}" has been deleted.'.format(media.metadata[u'title']), False)
    except Exception as e:
        map_exceptions(e)


# Environments management ----------------------------------------------------------------------------------------------

@app.route(u'/environment/count', methods=[u'GET'])
def api_environment_count():
    """
    Return the number of environments.

    **Example request**:

    .. warning:: TODO
    """
    try:
        requires_auth(request=request, allow_root=True, role=u'admin_platform')
        (environments, default) = orchestra.get_environments()
        return ok_200(len(environments), False)
    except Exception as e:
        map_exceptions(e)


@app.route(u'/environment/HEAD', methods=[u'GET'])
def api_environment_get_head():
    """
    Return an array containing the environments serialized to JSON.

    **Example request**:

    .. warning:: TODO
    """
    try:
        requires_auth(request=request, allow_root=True, role=u'admin_platform')
        (environments, default) = orchestra.get_environments()
        return ok_200({u'environments': environments, u'default': default}, False)
    except Exception as e:
        map_exceptions(e)


@app.route(u'/environment', methods=[u'GET'])
def api_environment_get():
    """
    Return an array containing the environments (with status) serialized to JSON.

    **Example request**:

    .. warning:: TODO
    """
    try:
        requires_auth(request=request, allow_root=True, role=u'admin_platform')
        (environments, default) = orchestra.get_environments(get_status=True)
        return ok_200({u'environments': environments, u'default': default}, False)
    except Exception as e:
        map_exceptions(e)


@app.route(u'/environment', methods=[u'POST'])
def api_environment_post():
    """
    Add a new environment.

    **Example request**:

    .. warning:: TODO
    """
    try:
        requires_auth(request=request, allow_root=True, role=u'admin_platform')
        data = get_request_data(request, qs_only_first_value=True)
        return ok_200(orchestra.add_environment(data[u'name'], data[u'type'], data[u'region'], data[u'access_key'],
                      data[u'secret_key'], data[u'control_bucket']), False)
    except Exception as e:
        map_exceptions(e)


@app.route(u'/environment/name/<name>/HEAD', methods=[u'GET'])
def api_environment_name_get_head(name):
    u"""
    Return an environment containing his status serialized to JSON.

    **Example request**:

    .. warning:: TODO
    """
    try:
        requires_auth(request=request, allow_root=True, role=u'admin_platform')
        return ok_200(orchestra.get_environments(name), False)
    except Exception as e:
        map_exceptions(e)


@app.route(u'/environment/name/<name>', methods=[u'GET'])
def api_environment_name_get(name):
    u"""
    Return an environment serialized to JSON.

    **Example request**:

    .. warning:: TODO
    """
    try:
        requires_auth(request=request, allow_root=True, role=u'admin_platform')
        return ok_200(orchestra.get_environment(name, get_status=True), False)
    except Exception as e:
        map_exceptions(e)


@app.route(u'/environment/name/<name>', methods=[u'DELETE'])
def api_environment_name_delete(name):
    """
    Remove an environment (destroy services and unregister it).

    **Example request**:

    .. warning:: TODO
    """
    try:
        requires_auth(request=request, allow_root=True, role=u'admin_platform')
        return ok_200(orchestra.delete_environment(name, remove=True), False)
    except Exception as e:
        map_exceptions(e)


# Transformation profiles management -----------------------------------------------------------------------------------

@app.route(u'/transform/profile/encoder', methods=[u'GET'])
def api_transform_profile_encoder():
    """
    Return an array containing the names of the available encoders.

    **Example request**:

    .. sourcecode:: http

        GET /transform/profile/encoder HTTP/1.1
        Host: somewhere.com
        Header: martin@oscied.org:oscied
        Accept: application/json

    **Example response**:

    .. sourcecode:: http

        HTTP/1.1 200 OK
        Vary: Accept
        Content-Type: application/json

        {
          "status": 200,
          "value": ["copy", "ffmpeg", "dashcast"]
        }

    :Allowed: Any user
    :statuscode 200: OK
    :statuscode 401: Authenticate.
    :statuscode 403: Authentication Failed.
    """
    try:
        requires_auth(request=request, allow_any=True)
        return ok_200(orchestra.get_transform_profile_encoders(), True)
    except Exception as e:
        map_exceptions(e)


@app.route(u'/transform/profile/count', methods=[u'GET'])
def api_transform_profile_count():
    """
    Return the number of transformation profiles.

    **Example request**:

    .. sourcecode:: http

        GET /transform/profile/count HTTP/1.1
        Host: somewhere.com
        Header: nabil@oscied.org:oscied
        Accept: application/json

    **Example response**:

    .. sourcecode:: http

        HTTP/1.1 200 OK
        Vary: Accept
        Content-Type: application/json

        {"status": 200, "value": 100}

    :Allowed: Any user
    :statuscode 200: OK
    :statuscode 401: Authenticate.
    :statuscode 403: Authentication Failed.
    """
    try:
        requires_auth(request=request, allow_any=True)
        data = get_request_data(request, accepted_keys=orchestra.db_count_keys, qs_only_first_value=True, fail=False)
        return ok_200(orchestra.get_transform_profiles_count(**data), False)
    except Exception as e:
        map_exceptions(e)


@app.route(u'/transform/profile', methods=[u'GET'])
def api_transform_profile_get():
    """
    Return an array containing the transformation profiles serialized to JSON.

    **Example request**:

    .. sourcecode:: http

        GET /transform/profile HTTP/1.1
        Host: somewhere.com
        Header: michel@oscied.org:oscied
        Accept: application/json

    **Example response**:

    .. sourcecode:: http

        HTTP/1.1 200 OK
        Vary: Accept
        Content-Type: application/json

        {
          "status": 200,
          "value": [{"_id": "...", "...": "..."}, {"_id": "..."}]}

    :Allowed: Any user
    :statuscode 200: OK
    :statuscode 401: Authenticate.
    :statuscode 403: Authentication Failed.
    """
    try:
        requires_auth(request=request, allow_any=True)
        data = get_request_data(request, accepted_keys=orchestra.db_find_keys, qs_only_first_value=True, fail=False)
        return ok_200(orchestra.get_transform_profiles(**data), True)
    except Exception as e:
        map_exceptions(e)


@app.route(u'/transform/profile', methods=[u'POST'])
def api_transform_profile_post():
    """
    Add a transformation profile.

    The transformation profile's ``encoder_name`` attribute can be the following :

    * **copy** to bypass FFmpeg and do a simple file block copy ;
    * **ffmpeg** to transcode a media asset to another with FFMpeg ;
    * **dashcast** to transcode a media asset to MPEG-DASH with DashCast ;

    **Example request**:

    .. sourcecode:: http

        POST /transform/profile HTTP/1.1
        Host: somewhere.com
        Header: daniel@oscied.org:oscied
        Accept: application/json
        Content-Type: application/json

        {
          "title": "To MP4",
          "description": "Convert to MP4 (container)",
          "encoder_name": "ffmpeg",
          "encoder_string": "-acodec copy -vcodec copy -f mp4"
        }

    **Example response**:

    .. sourcecode:: http

        HTTP/1.1 200 OK
        Vary: Accept
        Content-Type: application/json

        {
          "status": 200,
          "value": {
            "_id": "c316ff1a-74f8-11e2-82d4-3085a9accd33",
            "title": "To MP4",
            "description": "Convert to MP4 (container)",
            "encoder_name": "ffmpeg",
            "encoder_string": "-acodec copy -vcodec copy -f mp4"
          }
        }

    :Allowed: Any user
    :query title: New profile's title (required)
    :query description: New profile's description (required)
    :query encoder_name: New profile's encoder name (required)
    :query encoder_string: New profile's encoder-specific string (optional)
    :statuscode 200: OK
    :statuscode 400: Key ``key`` not found. *or* on type or value error
    :statuscode 400: Duplicate transformation profile title ``profile``.
    :statuscode 401: Authenticate.
    :statuscode 403: Authentication Failed.
    :statuscode 415: Requires (valid) json content-type.
    """
    try:
        requires_auth(request=request, allow_any=True)
        data = get_request_data(request, qs_only_first_value=True)
        profile = TransformProfile(title=data[u'title'], description=data[u'description'],
                                   encoder_name=data[u'encoder_name'], encoder_string=data[u'encoder_string'])
        orchestra.save_transform_profile(profile)
        return ok_200(profile, True)
    except Exception as e:
        map_exceptions(e)


@app.route(u'/transform/profile/id/<id>', methods=[u'GET'])
def api_transform_profile_id_get(id):
    """
    Return a transformation profile serialized to JSON.

    **Example request**:

    .. sourcecode:: http

        GET /transform/profile/id/c316ff1a-74f8-11e2-82d4-3085a9accd33 HTTP/1.1
        Host: somewhere.com
        Header: francois@oscied.org:oscied
        Accept: application/json

    **Example response**:

    .. sourcecode:: http

        HTTP/1.1 200 OK
        Vary: Accept
        Content-Type: application/json

        {
          "status": 200,
          "value": {
            "_id": "c316ff1a-74f8-11e2-82d4-3085a9accd33",
            "title": "To MP4",
            "description": "Convert to MP4 (container)",
            "encoder_name": "ffmpeg",
            "encoder_string": "-acodec copy -vcodec copy -f mp4"
          }
        }

    :Allowed: Any user
    :param id: id of profile to get
    :statuscode 200: OK
    :statuscode 401: Authenticate.
    :statuscode 403: Authentication Failed.
    :statuscode 404: No transformation profile with id ``id``.
    :statuscode 415: Wrong id format ``id``.
    """
    try:
        check_id(id)
        requires_auth(request=request, allow_any=True)
        profile = orchestra.get_transform_profile(spec={u'_id': id})
        if not profile:
            raise IndexError(to_bytes(u'No transformation profile with id {0}.'.format(id)))
        return ok_200(profile, True)
    except Exception as e:
        map_exceptions(e)


@app.route(u'/transform/profile/id/<id>', methods=[u'DELETE'])
def api_transform_profile_id_delete(id):
    """
    Delete a transformation profile.

    **Example request**:

    .. sourcecode:: http

        DELETE /transform/profile/id/c316ff1a-(...)-3085a9accd33 HTTP/1.1
        Host: somewhere.com
        Header: dimitri@oscied.org:oscied
        Accept: application/json

    **Example response**:

    .. sourcecode:: http

        HTTP/1.1 200 OK
        Vary: Accept
        Content-Type: application/json

        {
          "status": 200,
          "value": "The transformation profile \\"To MP4\\" has been deleted."
        }

    :Allowed: Any user
    :param id: id of profile to delete
    :statuscode 200: OK
    :statuscode 401: Authenticate.
    :statuscode 403: Authentication Failed.
    :statuscode 404: No transformation profile with id ``id``.
    :statuscode 415: Wrong id format ``id``.
    """
    try:
        check_id(id)
        requires_auth(request=request, allow_any=True)
        profile = orchestra.get_transform_profile(spec={u'_id': id})
        if not profile:
            raise IndexError(to_bytes(u'No transformation profile with id {0}.'.format(id)))
        orchestra.delete_transform_profile(profile)
        return ok_200(u'The transformation profile "{0}" has been deleted.'.format(profile.title), False)
    except Exception as e:
        map_exceptions(e)


# Transformation units management (encoders) ---------------------------------------------------------------------------

@app.route(u'/transform/unit/environment/<environment>/count', methods=[u'GET'])
def api_transform_unit_count(environment):
    """
    Return number of transformation units in the environment ``environment``.

    **Example request**:

    .. warning:: TODO
    """
    try:
        requires_auth(request=request, allow_root=True, allow_any=True)
        return ok_200(orchestra.get_transform_units_count(environment), False)
    except Exception as e:
        map_exceptions(e)


@app.route(u'/transform/unit/environment/<environment>', methods=[u'GET'])
def api_transform_unit_get(environment):
    """
    Return an array containing the transformation units of environment ``environment`` serialized to
    JSON.

    **Example request**:

    .. warning:: TODO
    """
    try:
        requires_auth(request=request, allow_root=True, allow_any=True)
        return ok_200(orchestra.get_transform_units(environment), False)
    except Exception as e:
        map_exceptions(e)


@app.route(u'/transform/unit/environment/<environment>', methods=[u'POST'])
def api_transform_unit_post(environment):
    """
    Ensure that ``num_units`` transformation units are deployed into environment ``environment``.

    **Example request**:

    .. warning:: TODO
    """
    try:
        requires_auth(request=request, allow_root=True, role=u'admin_platform')
        data = get_request_data(request, qs_only_first_value=True)
        orchestra.ensure_num_transform_units(environment, int(data[u'num_units']), terminate=True)
        return ok_200(u'Ensured {0} transformation units into environment "{1}"'.format(data[u'num_units'],
                      environment), False)
    except Exception as e:
        map_exceptions(e)


@app.route(u'/transform/unit/environment/<environment>', methods=[u'DELETE'])
def api_transform_unit_delete(environment):
    """
    Remove the transformation service from environment ``environment``.

    **Example request**:

    .. warning:: TODO
    """
    try:
        requires_auth(request=request, allow_root=True, role=u'admin_platform')
        orchestra.ensure_transform_units(environment, None, terminate=True)
        return ok_200(u'Removed transformation service from environment "{0}"'.format(environment), False)
    except Exception as e:
        map_exceptions(e)


@app.route(u'/transform/unit/environment/<environment>/number/<number>', methods=[u'GET'])
def api_transform_unit_number_get(environment, number):
    """
    Return a transformation unit serialized to JSON.

    **Example request**:

    .. warning:: TODO
    """
    try:
        requires_auth(request=request, allow_root=True, allow_any=True)
        unit = orchestra.get_transform_unit(environment, number)
        if not unit:
            raise IndexError(to_bytes(u'Transformation unit {0} not found in environment {1}.'.format(number,
                             environment)))
        return ok_200(unit, True)
    except Exception as e:
        map_exceptions(e)


@app.route(u'/transform/unit/environment/<environment>/number/<number>', methods=[u'DELETE'])
def api_transform_unit_number_delete(environment, number):
    """
    Remove the transformation unit number ``number`` from environment ``environment``.

    **Example request**:

    .. warning:: TODO
    """
    try:
        requires_auth(request=request, allow_root=True, role=u'admin_platform')
        orchestra.destroy_transform_unit(environment, number, terminate=True)
        return ok_200(u'The transformation unit {0} has been removed from environment {1}.'.format(number, environment),
                      False)
    except Exception as e:
        map_exceptions(e)


# Transformation tasks (encoding) --------------------------------------------------------------------------------------

@app.route(u'/transform/queue', methods=[u'GET'])
def api_transform_queue():
    """
    Return an array containing the transformation queues serialized to JSON.

    **Example request**:

    .. sourcecode:: http

        GET /transform/queue HTTP/1.1
        Host: somewhere.com
        Header: marco@oscied.org:oscied
        Accept: application/json

    **Example response**:

    .. sourcecode:: http

        HTTP/1.1 200 OK
        Vary: Accept
        Content-Type: application/json

        {
          "status": 200,
          "value": ["transform_amazon", "transform_ebu_geneva"]
        }

    :Allowed: Any user
    :statuscode 200: OK
    :statuscode 401: Authenticate.
    :statuscode 403: Authentication Failed.
    """
    try:
        requires_auth(request=request, allow_any=True)
        return ok_200(orchestra.get_transform_queues(), True)
    except Exception as e:
        map_exceptions(e)


@app.route(u'/transform/task/count', methods=[u'GET'])
def api_transform_task_count():
    """
    Return the number of transformation tasks.

    **Example request**:

    .. sourcecode:: http

        GET /transform/task/count HTTP/1.1
        Host: somewhere.com
        Header: marylene@oscied.org:oscied
        Accept: application/json

    **Example response**:

    .. sourcecode:: http

        HTTP/1.1 200 OK
        Vary: Accept
        Content-Type: application/json

        {"status": 200, "value": 15260}

    :Allowed: Any user
    :statuscode 200: OK
    :statuscode 401: Authenticate.
    :statuscode 403: Authentication Failed.
    """
    try:
        requires_auth(request=request, allow_any=True)
        data = get_request_data(request, accepted_keys=orchestra.db_count_keys, qs_only_first_value=True, fail=False)
        return ok_200(orchestra.get_transform_tasks_count(**data), False)
    except Exception as e:
        map_exceptions(e)


@app.route(u'/transform/task/HEAD', methods=[u'GET'])
def api_transform_task_head():
    """
    Return an array containing the transformation tasks serialized as JSON.

    The transformation tasks attributes are appended with the Celery's ``async result`` of the tasks.

    **Example request**:

    .. sourcecode:: http

        GET /transform/task/HEAD HTTP/1.1
        Host: somewhere.com
        Header: thomas@oscied.org:oscied
        Accept: application/json

    **Example response**:

    .. sourcecode:: http

        HTTP/1.1 200 OK
        Vary: Accept
        Content-Type: application/json

        {
          "status": 200,
          "value": [{"_id": "...", "...": "..."}, {"_id": "..."}]
        }

    :Allowed: Any user
    :statuscode 200: OK
    :statuscode 401: Authenticate.
    :statuscode 403: Authentication Failed.
    """
    try:
        requires_auth(request=request, allow_any=True)
        data = get_request_data(request, accepted_keys=orchestra.db_find_keys, qs_only_first_value=True, fail=False)
        return ok_200(orchestra.get_transform_tasks(**data), True)
    except Exception as e:
        map_exceptions(e)


@app.route(u'/transform/task', methods=[u'GET'])
def api_transform_task_get():
    """
    Return an array containing the transformation tasks serialized to JSON.

    The transformation tasks attributes are appended with the Celery's ``async result`` of the tasks.

    All ``thing_id`` fields are replaced by corresponding ``thing``.
    For example ``user_id`` is replaced by ``user``'s data.

    **Example request**:

    .. sourcecode:: http

        GET /transform/task HTTP/1.1
        Host: somewhere.com
        Header: antoinette@oscied.org:oscied
        Accept: application/json

    **Example response**:

    .. sourcecode:: http

        HTTP/1.1 200 OK
        Vary: Accept
        Content-Type: application/json

        {
          "status": 200,
          "value": [{"_id": "...", "...": "..."}, {"_id": "..."}]
        }

    :Allowed: Any user
    :statuscode 200: OK
    :statuscode 401: Authenticate.
    :statuscode 403: Authentication Failed.
    """
    try:
        requires_auth(request=request, allow_any=True)
        data = get_request_data(request, accepted_keys=orchestra.db_find_keys, qs_only_first_value=True, fail=False)
        return ok_200(orchestra.get_transform_tasks(load_fields=True, **data), True)
    except Exception as e:
        map_exceptions(e)


@app.route(u'/transform/task', methods=[u'POST'])
def api_transform_task_post():
    """
    Launch a transformation task.

    Any user can launch a transformation task using any media asset as input and any transformation profile.
    This is linked to media assets and transformation profile API methods access policies.

    The output media asset is registered to the database with the PENDING status and the ``parent_id`` field is set to
    input media asset's ``id``. This permit to know relation between media assets !

    The orchestrator will automatically add ``add_date`` to ``statistic``.

    .. note::

        Interesting enhancement would be to :

        * Schedule obs by specifying start time (...) ;
        * Handle the registration of tasks related to PENDING medias ;

    **Example request**:

    .. sourcecode:: http

        POST /transform/task HTTP/1.1
        Host: somewhere.com
        Header: tabby@bernex.ch:miaow
        Accept: application/json
        Content-Type: application/json

        {
          "media_in_id": "a396fe66-74ee-11e2-89ad-3085a9accbb8",
          "profile_id": "c316ff1a-74f8-11e2-82d4-3085a9accd33",
          "filename": "avatar.mp4",
          "metadata": {"title": "Avatar (1080p)"},
          "send_email": "true",
          "queue": "transform_ebu-geneva"
        }

    **Example response**:

    .. sourcecode:: http

        HTTP/1.1 200 OK
        Vary: Accept
        Content-Type: application/json

        {"status": 200, "value": "ea9088f0-74f8-11e2-b780-3085a9acccb2a"}

    :Allowed: Any user
    :query media_in_id: New task input media's id (required)
    :query profile_id: New task profile's id (required)
    :query filename: New task output media's filename (required)
    :query metadata: New  task output media's metadata (required)
    :query send_email: Toggle e-mail delivery (required)
    :query queue: The transformation queue used to route the new task (required)
    :statuscode 200: OK
    :statuscode 400: Key ``key`` not found. *or* on type or value error
    :statuscode 400: Unable to transmit task to workers of queue ``queue``.
    :statuscode 401: Authenticate.
    :statuscode 403: Authentication Failed.
    :statuscode 404: No user with id ``id``.
    :statuscode 404: No media asset with id ``media_in_id``.
    :statuscode 404: No profile with id ``profile_id``.
    :statuscode 404: No transformation queue with name ``queue``.
    :statuscode 415: Required (valid) json content-type.
    :statuscode 501: Cannot launch the task, input media asset's status is ``status``.
    """
    try:
        auth_user = requires_auth(request=request, allow_any=True)
        data = get_request_data(request, qs_only_first_value=True)
        task_id = orchestra.launch_transform_task(
            auth_user._id, data[u'media_in_id'], data[u'profile_id'], data[u'filename'], data[u'metadata'],
            data[u'send_email'], data[u'queue'], u'/transform/callback')
        return ok_200(task_id, True)
    except Exception as e:
        map_exceptions(e)


# FIXME why HEAD verb doesn't work (curl: (18) transfer closed with 263 bytes remaining to read) ?
@app.route(u'/transform/task/id/<id>/HEAD', methods=[u'GET'])
def api_transform_task_id_head(id):
    """
    Return a transformation task serialized to JSON.

    The transformation task attributes are appended with the Celery's ``async result`` of the task.

    **Example request**:

    .. sourcecode:: http

        GET /transform/task/id/48c111c8-74f8-11e2-a7a8-3085a9acc6c4/HEAD HTTP/1.1
        Host: somewhere.com
        Header: edoardo@oscied.org:oscied
        Accept: application/json
        Content-Type: application/json

    **Example response**:

    Floating numbers are here with "" for autoflask to work !!

    .. sourcecode:: http

        HTTP/1.1 200 OK
        Vary: Accept
        Content-Type: application/json

        {
          "status": 200,
          "value": {
            "_id": "48c111c8-74f8-11e2-a7a8-3085a9acc6c4",
            "user_id": "4e8a1bce-74f3-11e2-9660-3085a9acce0b",
            "media_in_id": "a8a165b8-74f7-11e2-a59e-3085a9acc049",
            "media_out_id": "52ea73ac-74f3-11e2-afdb-3085a9acc5ff",
            "profile_id": "55da66d6-74f3-11e2-9dff-3085a9acce4e",
            "statistic": {
              "add_date": "2013-02-11 22:44",
              "start_date": "2013-02-11 22:44",
              "elapsed_time": "19.241864919662476",
              "eta_time": 0, "percent": 100,
              "media_in_size": 54871886, "media_in_duration": "00:02:44.88",
              "media_out_size": 25601528, "media_out_duration": "00:00:01.95"
            },
            "revoked": false,
            "status": "SUCCESS"
          }
        }

    :Allowed: Any user
    :param id: id of task to get
    :statuscode 200: OK
    :statuscode 401: Authenticate.
    :statuscode 403: Authentication Failed.
    :statuscode 404: No transformation task with id ``id``.
    :statuscode 415: Wrong id format ``id``.
    """
    try:
        check_id(id)
        requires_auth(request=request, allow_any=True)
        task = orchestra.get_transform_task(spec={u'_id': id})
        if not task:
            raise IndexError(to_bytes(u'No transformation task with id {0}.'.format(id)))
        return ok_200(task, True)
    except Exception as e:
        map_exceptions(e)


@app.route(u'/transform/task/id/<id>', methods=[u'GET'])
def api_transform_task_id_get(id):
    """
    Return a transformation task serialized to JSON.

    The transformation task attributes are appended with the Celery's ``async result`` of the task.

    All ``thing_id`` fields are replaced by corresponding ``thing``.
    For example ``user_id`` is replaced by ``user``'s data.

    **Example request**:

    .. sourcecode:: http

        GET /transform/task/id/ea9088f0-74f8-11e2-b780-3085a9acccb2a HTTP/1.1
        Host: somewhere.com
        Header: claire@oscied.org:oscied
        Accept: application/json
        Content-Type: application/json

    **Example response**:

    Floating numbers are here with "" for autoflask to work !!

    .. sourcecode:: http

        HTTP/1.1 200 OK
        Vary: Accept
        Content-Type: application/json

        {
          "status": 200,
          "value": {
            "_id": "48c111c8-74f8-11e2-a7a8-3085a9acc6c4",
            "user": {
              "_id": "4e8ec55e-74f7-11e2-8451-3085a9acc8e0b",
              "first_name": "David",
              "last_name": "Fischer",
              "name": "David Fischer",
              "mail": "d@f.com",
              "admin_platform": true
            },
            "media_in": {
              "_id": "a8a165b8-74f7-11e2-a59e-3085a9acc049",
              "user_id": "4e8a1bce-74f3-11e2-9660-3085a9acce0b",
              "parent_id": null,
              "uri": "glusterfs://<address>/medias_volume/medias/
                      <user_id>/<media_id>",
              "public_uris": {
                "c697f528-74f7-11e2-96a3-3085a9accc5d":
                "http://10.0.3.254/medias/<user_id>/<media_id>/
                 Project_London_trailer_2009.mp4"
              },
              "filename": "Project_London_trailer_2009.mp4",
              "metadata": {
                "add_date": "2013-02-11 22:37",
                "duration": "00:02:44.88", "size": 54871886,
                "title": "Project London - Official Trailer (2009)"
              },
              "status": "READY"
            },
            "media_out": {
              "_id": "52ea73ac-74f3-11e2-afdb-3085a9acc5ff",
              "user_id": "4e8ec55e-74f7-11e2-8451-3085a9acc8e0b",
              "parent_id": "a8a165b8-74f7-11e2-a59e-3085a9acc049",
              "uri": "glusterfs://<address>/medias_volume/medias/
                      <user_id>/<media_id>",
              "public_uris": null,
              "filename": "project_london.mp2",
              "metadata": {
                "add_date": "2013-02-11 22:44",
                "duration": "00:00:01.95", "size": 25601528,
                "title": "Project London MP2"
              }
              "status": "READY"
            },
            "profile": {
              "_id": "55da66d6-74f3-11e2-9dff-3085a9acce4e",
              "title": "To MP2",
              "description":
                "Convert video track to MPEG-2 format, copy audio track",
              "encoder_name": "ffmpeg",
              "encoder_string":
                "-acodec copy -vcodec mpeg2video -f mpeg2video"
            },
            "statistic": {
                "add_date": "2013-02-11 22:44",
                "start_date": "2013-02-11 22:44",
                "elapsed_time": "19.241864919662476",
                "eta_time": 0, "percent": 100,
                "media_in_size": 54871886, "media_in_duration": "00:02:44.88",
                "media_out_size": 25601528, "media_out_duration": "00:00:01.95"
            },
            "revoked": false,
            "status": "SUCCESS"
          }
        }

    :Allowed: Any user
    :param id: id of task to get
    :statuscode 200: OK
    :statuscode 401: Authenticate.
    :statuscode 403: Authentication Failed.
    :statuscode 404: No transformation task with id ``id``.
    :statuscode 415: Wrong id format ``id``.
    """
    try:
        check_id(id)
        requires_auth(request=request, allow_any=True)
        task = orchestra.get_transform_task(spec={u'_id': id}, load_fields=True)
        if not task:
            raise IndexError(to_bytes(u'No transformation task with id {0}.'.format(id)))
        return ok_200(task, True)
    except Exception as e:
        map_exceptions(e)


@app.route(u'/transform/task/id/<id>', methods=[u'DELETE'])
def api_transform_task_id_delete(id):
    """
    Revoke a transformation task.

    This method do not delete tasks from tasks database but set ``revoked`` attribute in tasks database and broadcast
    revoke request to transformation units with Celery. If the task is actually running it will be canceled.
    The output media asset will be deleted.

    **Example request**:

    .. sourcecode:: http

        DELETE /transform/task/id/ea9088f0-74f8-11e2-b780-3085a9acccb2a HTTP/1.1
        Host: somewhere.com
        Header: tabby@bernex.ch:miaow
        Accept: application/json
        Content-Type: application/json

    **Example response**:

    .. sourcecode:: http

        HTTP/1.1 200 OK
        Vary: Accept
        Content-Type: application/json

        {
          "status": 200,
          "value": "The transformation task \\"<task_id>\\" has been revoked.
                    Corresponding output media asset will be deleted."
        }

    :Allowed: Only author of the task
    :param id: id of task to delete
    :statuscode 200: OK
    :statuscode 400: on value error
    :statuscode 400: Transformation task ``id`` is already revoked !
    :statuscode 400: Cannot revoke a transformation task with status ``status``.
    :statuscode 401: Authenticate.
    :statuscode 403: Authentication Failed.
    :statuscode 403: You are not allowed to revoke transformation task with id ``id``.
    :statuscode 404: No transformation task with id ``id``.
    :statuscode 415: Wrong id format ``id``.
    """
    try:
        check_id(id)
        auth_user = requires_auth(request=request, allow_any=True)
        task = orchestra.get_transform_task(spec={u'_id': id})
        if not task:
            raise IndexError(to_bytes(u'No transformation task with id {0}.'.format(id)))
        if auth_user._id != task.user_id:
            abort(403, u'You are not allowed to revoke transformation task with id {0}.'.format(id))
        orchestra.revoke_transform_task(task=task, terminate=True, remove=False, delete_media=True)
        return ok_200(u'The transformation task "{0}" has been revoked. Corresponding output media asset will be delete'
                      'd.'.format(task._id), False)
    except Exception as e:
        map_exceptions(e)


# Publication units management -----------------------------------------------------------------------------------------

@app.route(u'/publisher/unit/environment/<environment>/count', methods=[u'GET'])
def api_publisher_unit_count(environment):
    """
    Return publication units count of environment ``environment``.

    **Example request**:

    .. warning:: TODO
    """
    try:
        requires_auth(request=request, allow_root=True, allow_any=True)
        return ok_200(orchestra.get_publisher_units_count(environment), False)
    except Exception as e:
        map_exceptions(e)


@app.route(u'/publisher/unit/environment/<environment>', methods=[u'GET'])
def api_publisher_unit_get(environment):
    """
    Return an array containing the publication units of environment ``environment`` serialized to JSON.

    **Example request**:

    .. warning:: TODO
    """
    try:
        requires_auth(request=request, allow_root=True, allow_any=True)
        return ok_200(orchestra.get_publisher_units(environment), False)
    except Exception as e:
        map_exceptions(e)


@app.route(u'/publisher/unit/environment/<environment>', methods=[u'POST'])
def api_publisher_unit_post(environment):
    """
    Ensure that ``num_units`` publication units are deployed into environment ``environment``.

    **Example request**:

    .. warning:: TODO
    """
    try:
        requires_auth(request=request, allow_root=True, role=u'admin_platform')
        data = get_request_data(request, qs_only_first_value=True)
        orchestra.ensure_publisher_units(environment, int(data[u'num_units']), terminate=True)
        return ok_200(u'Ensured {0} publication units into environment "{1}"'.format(data[u'num_units'], environment),
                      False)
    except Exception as e:
        map_exceptions(e)


@app.route(u'/publisher/unit/environment/<environment>', methods=[u'DELETE'])
def api_publisher_unit_delete(environment):
    """
    Remove the publication service from environment ``environment``.

    **Example request**:

    .. warning:: TODO
    """
    try:
        requires_auth(request=request, allow_root=True, role=u'admin_platform')
        orchestra.destroy_publisher_units(environment, None, terminate=True)
        return ok_200(u'Removed publication service from environment "{0}"'.format(environment), False)
    except Exception as e:
        map_exceptions(e)


@app.route(u'/publisher/unit/environment/<environment>/number/<number>', methods=[u'GET'])
def api_publisher_unit_number_get(environment, number):
    """
    Return a publication unit serialized to JSON.

    **Example request**:

    .. warning:: TODO
    """
    try:
        requires_auth(request=request, allow_root=True, allow_any=True)
        unit = orchestra.get_publisher_unit(environment, number)
        if not unit:
            raise IndexError(to_bytes(u'Publication unit {0} not found in environment {1}.'.format(
                             number, environment)))
        return ok_200(unit, True)
    except Exception as e:
        map_exceptions(e)


@app.route(u'/publisher/unit/environment/<environment>/number/<number>', methods=[u'DELETE'])
def api_publisher_unit_number_delete(environment, number):
    """
    Remove publication unit number ``number`` from environment ``environment``.

    **Example request**:

    .. warning:: TODO
    """
    try:
        requires_auth(request=request, allow_root=True, role=u'admin_platform')
        orchestra.destroy_publisher_unit(environment, number, terminate=True)
        return ok_200(u'The publication unit {0} has been removed of environment {1}.'.format(number, environment),
                      False)
    except Exception as e:
        map_exceptions(e)


# Publishing tasks -----------------------------------------------------------------------------------------------------

@app.route(u'/publisher/queue', methods=[u'GET'])
def api_publisher_queue():
    """
    Return an array containing the publication queues.

    **Example request**:

    .. sourcecode:: http

        GET /publisher/queue HTTP/1.1
        Host: somewhere.com
        Header: jean-claude@oscied.org:oscied
        Accept: application/json

    **Example response**:

    .. sourcecode:: http

        HTTP/1.1 200 OK
        Vary: Accept
        Content-Type: application/json

        {
          "status": 200,
          "value": ["publisher_london", "publisher_ebu_geneva"]
        }

    :Allowed: Any user
    :statuscode 200: OK
    :statuscode 401: Authenticate.
    :statuscode 403: Authentication Failed.
    """
    try:
        requires_auth(request=request, allow_any=True)
        return ok_200(orchestra.get_publisher_queues(), True)
    except Exception as e:
        map_exceptions(e)


@app.route(u'/publisher/task/count', methods=[u'GET'])
def api_publisher_task_count():
    """
    Return the number of publication tasks.

    **Example request**:

    .. sourcecode:: http

        GET /publisher/task/count HTTP/1.1
        Host: somewhere.com
        Header: sophie@oscied.org:oscied
        Accept: application/json

    **Example response**:

    .. sourcecode:: http

        HTTP/1.1 200 OK
        Vary: Accept
        Content-Type: application/json

        {"status": 200, "value": 3904}

    :Allowed: Any user
    :statuscode 200: OK
    :statuscode 401: Authenticate.
    :statuscode 403: Authentication Failed.
    """
    try:
        requires_auth(request=request, allow_any=True)
        data = get_request_data(request, accepted_keys=orchestra.db_count_keys, qs_only_first_value=True, fail=False)
        return ok_200(orchestra.get_publisher_tasks_count(**data), False)
    except Exception as e:
        map_exceptions(e)


@app.route(u'/publisher/task/HEAD', methods=[u'GET'])
def api_publisher_task_head():
    """
    Return an array containing the publication tasks serialized as JSON.

    The publication tasks attributes are appended with the Celery's ``async result`` of the tasks.

    **Example request**:

    .. sourcecode:: http

        GET /publisher/task/HEAD HTTP/1.1
        Host: somewhere.com
        Header: antonin@oscied.org:oscied
        Accept: application/json

    **Example response**:

    .. sourcecode:: http

        HTTP/1.1 200 OK
        Vary: Accept
        Content-Type: application/json

        {
          "status": 200,
          "value": [{"_id": "...", "...": "..."}, {"_id": "..."}]
        }

    :Allowed: Any user
    :statuscode 200: OK
    :statuscode 401: Authenticate.
    :statuscode 403: Authentication Failed.
    """
    try:
        requires_auth(request=request, allow_any=True)
        data = get_request_data(request, accepted_keys=orchestra.db_find_keys, qs_only_first_value=True, fail=False)
        return ok_200(orchestra.get_publisher_tasks(**data), True)
    except Exception as e:
        map_exceptions(e)


@app.route(u'/publisher/task', methods=[u'GET'])
def api_publisher_task_get():
    """
    Return an array containing the publication tasks serialized to JSON.

    The publication tasks attributes are appended with the Celery's ``async result`` of the tasks.

    All ``thing_id`` fields are replaced by corresponding ``thing``.
    For example ``user_id`` is replaced by ``user``'s data.

    **Example request**:

    .. sourcecode:: http

        GET /publisher/task HTTP/1.1
        Host: somewhere.com
        Header: melanie@oscied.org:oscied
        Accept: application/json

    **Example response**:

    .. sourcecode:: http

        HTTP/1.1 200 OK
        Vary: Accept
        Content-Type: application/json

        {
          "status": 200,
          "value": [{"_id": "...", "...": "..."}, {"_id": "..."}]
        }

    :Allowed: Any user
    :statuscode 200: OK
    :statuscode 401: Authenticate.
    :statuscode 403: Authentication Failed.
    """
    try:
        requires_auth(request=request, allow_any=True)
        data = get_request_data(request, accepted_keys=orchestra.db_find_keys, qs_only_first_value=True, fail=False)
        return ok_200(orchestra.get_publisher_tasks(load_fields=True, **data), True)
    except Exception as e:
        map_exceptions(e)


@app.route(u'/publisher/task', methods=[u'POST'])
def api_publisher_task_post():
    """
    Launch a publication task.

    Any user can launch a publication task using any media asset as input.
    This is linked to media asset API methods access policy.

    The orchestrator will automatically add ``add_date`` to ``statistic``.

    .. note::

        Interesting enhancements would be to :

        * Schedule tasks by specifying start time (...)
        * Handle the registration of tasks related to PENDING medias
        * Permit to publication a media asset on more than one (1) publication queue

    **Example request**:

    .. sourcecode:: http

        POST /publisher/task HTTP/1.1
        Host: somewhere.com
        Header: tabby@bernex.ch:miaow
        Accept: application/json
        Content-Type: application/json

        {
          "media_id": "a396fe66-74ee-11e2-89ad-3085a9accbb8",
          "send_email": "true",
          "queue": "publisher_london"
        }

    **Example response**:

    .. sourcecode:: http

        HTTP/1.1 200 OK
        Vary: Accept
        Content-Type: application/json

        {
          "status": 200,
          "value": "73abcf7e-74ef-11e2-9322-3085a9accc9b9"
        }

    :Allowed: Any user
    :query media_id: New task input media's id (required)
    :query send_email: Toggle e-mail delivery (required)
    :query queue: The publication queue used to route task (required)
    :statuscode 200: OK
    :statuscode 400: Key ``key`` not found. *or* on type or value error
    :statuscode 400: Unable to transmit task to workers of queue ``queue``.
    :statuscode 401: Authenticate.
    :statuscode 403: Authentication Failed.
    :statuscode 404: No user with id ``id``.
    :statuscode 404: No media asset with id ``media_id``.
    :statuscode 404: No publication queue with name ``queue``.
    :statuscode 415: Required (valid) json content-type.
    :statuscode 501: Cannot launch the task, input media asset's status is ``status``.
    :statuscode 501: Cannot launch the task, input media asset will be published by another task with id ``id``.
    """
    try:
        auth_user = requires_auth(request=request, allow_any=True)
        data = get_request_data(request, qs_only_first_value=True)
        task_id = orchestra.launch_publisher_task(auth_user._id, data[u'media_id'], data[u'send_email'], data[u'queue'],
                                                  u'/publisher/callback')
        return ok_200(task_id, True)
    except Exception as e:
        map_exceptions(e)


# FIXME why HEAD verb doesn't work (curl: (18) transfer closed with 263 bytes remaining to read) ?
@app.route(u'/publisher/task/id/<id>/HEAD', methods=[u'GET'])
def api_publisher_task_id_head(id):
    """
    Return a publication task serialized to JSON.

    The publication task attributes are appended with the Celery's ``async result`` of the task.

    **Example request**:

    .. sourcecode:: http

        GET /publisher/task/id/c697f528-74f7-11e2-96a3-3085a9accc5d/HEAD HTTP/1.1
        Host: somewhere.com
        Header: tabby@bernex.ch:miaow
        Accept: application/json

    **Example response**:

    Floating numbers are here with "" for autoflask to work !!

    .. sourcecode:: http

        HTTP/1.1 200 OK
        Vary: Accept
        Content-Type: application/json

        {
          "status": 200,
          "value": {
            "_id": "c697f528-74f7-11e2-96a3-3085a9accc5d"
            "user_id": "4e8ec55e-74f7-11e2-8451-3085a9acc8e0b",
            "media_id": "a8a165b8-74f7-11e2-a59e-3085a9acc049",
            "publish_uri": "http://<publish_uri>/medias/<user_id>/<media_id>/
                            Project_London_trailer_2009.mp4",
            "statistic":
            {
              "add_date": "2013-02-11 22:38",
              "start_date": "2013-02-11 22:38",
              "elapsed_time": "0.5068690776824951",
              "eta_time": 0, "percent": 100,
              "media_size": 54871886, "publish_size": 54871886,
              "pid": 18307, "hostname": "famille-local-oscied-publisher-0"
            },
            "revoked": false,
            "status": "SUCCESS"
          }
        }

    :Allowed: Any user
    :param id: id of task to get
    :statuscode 200: OK
    :statuscode 401: Authenticate.
    :statuscode 403: Authentication Failed.
    :statuscode 404: No publication task with id ``id``.
    """
    try:
        check_id(id)
        requires_auth(request=request, allow_any=True)
        task = orchestra.get_publisher_task(spec={u'_id': id})
        if not task:
            raise IndexError(to_bytes(u'No publication task with id {0}.'.format(id)))
        return ok_200(task, True)
    except Exception as e:
        map_exceptions(e)


@app.route(u'/publisher/task/id/<id>', methods=[u'GET'])
def api_publisher_task_id_get(id):
    """
    Return a publication task serialized to JSON.

    The publication task attributes are appended with the Celery's ``async result`` of the task.

    All ``thing_id`` fields are replaced by corresponding ``thing``.
    For example ``user_id`` is replaced by ``user``'s data.


    **Example request**:

    .. sourcecode:: http

        GET /publisher/task/id/c697f528-74f7-11e2-96a3-3085a9accc5d HTTP/1.1
        Host: somewhere.com
        Header: tabby@bernex.ch:miaow
        Accept: application/json

    **Example response**:

    Floating numbers are here with "" for autoflask to work !!

    .. sourcecode:: http

        HTTP/1.1 200 OK
        Vary: Accept
        Content-Type: application/json

        {
          "status": 200,
          "value": {
            "_id": "c697f528-74f7-11e2-96a3-3085a9accc5d",
            "publish_uri": "http://<address>/medias/<user_id>/<media_id>/
                            Project_London_trailer_2009.mp4",
            "media": {
              "_id": "a8a165b8-74f7-11e2-a59e-3085a9acc049",
              "user_id": "4e8ec55e-74f7-11e2-8451-3085a9acc8e0b",
              "parent_id": null,
              "uri": "glusterfs://<address>/medias_volume/medias/
                      <user_id>/<media_id>",
              "public_uris": {
                "c697f528-74f7-11e2-96a3-3085a9accc5d":
                "http://<address>/medias/<user_id>/<media_id>/
                 Project_London_trailer_2009.mp4"
              },
              "filename": "Project_London_trailer_2009.mp4",
              "metadata": {
                "duration": "00:02:44.88", "add_date": "2013-02-11 22:37",
                "size": 54871886,
                "title": "Project London - Official Trailer (2009)"
              },
              "status": "READY"
            },
            "user": { "name": "David Fischer", "...": "..." },
            "statistic": {
              "add_date": "2013-02-11 22:38", "start_date": "2013-02-11 22:38"
              "media_size": 54871886, "publish_size": 54871886,
              "elapsed_time": "0.5068690776824951",
              "eta_time": 0, "percent": 100,
              "pid": 18307, "hostname": "famille-local-oscied-publisher-0"
            },
            "revoked": false,
            "status": "SUCCESS"
          }
        }

    :Allowed: Any user
    :param id: id of task to get
    :statuscode 200: OK
    :statuscode 401: Authenticate.
    :statuscode 403: Authentication Failed.
    :statuscode 404: No publication task with id ``id``.
    """
    try:
        check_id(id)
        requires_auth(request=request, allow_any=True)
        task = orchestra.get_publisher_task(spec={u'_id': id}, load_fields=True)
        if not task:
            raise IndexError(to_bytes(u'No publication task with id {0}.'.format(id)))
        return ok_200(task, True)
    except Exception as e:
        map_exceptions(e)


@app.route(u'/publisher/task/id/<id>', methods=[u'DELETE'])
def api_publisher_task_id_delete(id):
    """
    Revoke a publication task.

    This method do not delete tasks from tasks database but set ``revoked`` attribute in tasks database and broadcast
    revoke request to publication units with Celery. If the task is actually running it will be canceled.
    The media asset will be removed from the publication unit.

    **Example request**:

    .. sourcecode:: http

        DELETE /pulish/task/id/c697f528-74f7-11e2-96a3-3085a9accc5d HTTP/1.1
        Host: somewhere.com
        Header: tabby@bernex.ch:miaow
        Accept: application/json
        Content-Type: application/json

    **Example response**:

    .. sourcecode:: http

        HTTP/1.1 200 OK
        Vary: Accept
        Content-Type: application/json

        {
          "status": 200,
          "value": "The publication task \\"<task_id>\\" has been revoked.
                    Corresponding media asset will be unpublished from here."
        }

    :Allowed: Only author of the task
    :param id: id of task to delete
    :statuscode 200: OK
    :statuscode 401: Authenticate.
    :statuscode 403: Authentication Failed.
    :statuscode 403: You are not allowed to revoke publication task with id ``id``.
    :statuscode 404: No publication task with id ``id``.
    :statuscode 415: Wrong id format ``id``.
    """
    try:
        check_id(id)
        auth_user = requires_auth(request=request, allow_any=True)
        task = orchestra.get_publisher_task(spec={u'_id': id})
        if not task:
            raise IndexError(to_bytes(u'No publication task with id {0}.'.format(id)))
        if auth_user._id != task.user_id:
            abort(403, u'You are not allowed to revoke publication task with id {0}.'.format(id))
        orchestra.revoke_publisher_task(task=task, callback_url=u'/publisher/revoke/callback', terminate=True,
                                      remove=False)
        return ok_200(u'The publication task "{0}" has been revoked. Corresponding media asset will be unpublished from'
                      ' here.'.format(task._id), False)
    except Exception as e:
        map_exceptions(e)


# Workers (nodes) hooks ------------------------------------------------------------------------------------------------

@app.route(u'/transform/callback', methods=[u'POST'])
def api_transform_task_hook():
    """
    This method is called by transformation workers when they finish their work.

    If task is successful, the orchestrator will set media's status to READY.
    Else, the orchestrator will append ``error_details`` to ``statistic`` attribute of task.

    The media asset will be deleted if task failed (even the worker already take care of that).

    **Example request**:

    .. sourcecode:: http

        POST /transform/callback HTTP/1.1
        Host: somewhere.com
        Header: node:abcdef
        Accept: application/json
        Content-Type: application/json

        {
          "task_id": "1b96dcd6-7460-11e2-a06d-3085a9accb47",
          "status": "SUCCESS"
        }

    **Example response**:

    .. sourcecode:: http

        HTTP/1.1 200 OK
        Vary: Accept
        Content-Type: application/json

        {"status": 200, "value": "Your work is much appreciated, thanks !"}

    :Allowed: Node
    :query task_id: Task's id (required)
    :query status: Task's status (SUCCESS) or error's details (required)
    :statuscode 200: OK
    :statuscode 400: Key ``key`` not found. *or* on type or value error
    :statuscode 401: Authenticate.
    :statuscode 403: Authentication Failed.
    :statuscode 404: No transformation task with id ``id``.
    :statuscode 404: Unable to find output media asset with id ``id``.
    :statuscode 415: Requires (valid) json content-type.
    """
    try:
        requires_auth(request=request, allow_node=True)
        data = get_request_data(request, qs_only_first_value=True)
        task_id, status = data[u'task_id'], data[u'status']
        logging.debug(u'task {0}, status {1}'.format (task_id, status))
        orchestra.transform_callback(task_id, status)
        return ok_200(u'Your work is much appreciated, thanks !', False)
    except Exception as e:
        map_exceptions(e)


@app.route(u'/publisher/callback', methods=[u'POST'])
def api_publisher_task_hook():
    """
    This method is called by publication workers when they finish their work.

    If the task is successful, the orchestrator will update ``publish_uri`` attribute of the task, set media asset's
    status to SUCCESS and update ``public_uris`` attribute.
    Else, the orchestrator will append ``error_details`` to ``statistic`` attribute of the task.

    **Example request**:

    .. sourcecode:: http

        POST /publisher/callback HTTP/1.1
        Host: somewhere.com
        Header: node:abcdef
        Accept: application/json
        Content-Type: application/json

        {
          "task_id": "1b96dcd6-7460-11e2-a06d-3085a9accb47",
          "publish_uri": "http://<address>/medias/<user_id>/<media_id>/
                          Project_London_trailer_2009.mp4",
          "status": "SUCCESS"
        }

    **Example response**:

    .. sourcecode:: http

        HTTP/1.1 200 OK
        Vary: Accept
        Content-Type: application/json

        {"status": 200, "value": "Your work is much appreciated, thanks !"}

    :Allowed: Node
    :query task_id: Task's id (required)
    :query publish_uri: Publication URI of the media asset (required)
    :query status: Task's status (SUCCESS) or error's details (required)
    :statuscode 200: OK
    :statuscode 400: Key ``key`` not found. *or* on type or value error
    :statuscode 401: Authenticate.
    :statuscode 403: Authentication Failed.
    :statuscode 404: No publication task with id ``id``.
    :statuscode 404: Unable to find media asset with id ``id``.
    :statuscode 415: Requires (valid) json content-type.
    """
    try:
        requires_auth(request=request, allow_node=True)
        data = get_request_data(request, qs_only_first_value=True)
        task_id = data[u'task_id']
        publish_uri = data[u'publish_uri'] if u'publish_uri' in data else None
        status = data[u'status']
        logging.debug(u'task {0}, publish_uri {1}, status {2}'.format(task_id, publish_uri, status))
        orchestra.publisher_callback(task_id, publish_uri, status)
        return ok_200(u'Your work is much appreciated, thanks !', False)
    except Exception as e:
        map_exceptions(e)


@app.route(u'/publisher/revoke/callback', methods=[u'POST'])
def api_revoke_publisher_task_hook():
    """
    This method is called by publication workers when they finish their work (revoke).

    If the task is successful, the orchestrator will update media asset's ``status`` and ``public_uris`` attribute.
    Else, the orchestrator will append ``error_details`` to ``statistic`` attribute of the task.

    **Example request**:

    .. sourcecode:: http

        POST /publisher/revoke/callback HTTP/1.1
        Host: somewhere.com
        Header: node:abcdef
        Accept: application/json
        Content-Type: application/json

        {
          "task_id": "1b96dcd6-7460-11e2-a06d-3085a9accb47",
          "publish_uri": "http://<address>/medias/<user_id>/<media_id>/
                          Project_London_trailer_2009.mp4",
          "status": "SUCCESS"
        }

    **Example response**:

    .. sourcecode:: http

        HTTP/1.1 200 OK
        Vary: Accept
        Content-Type: application/json

        {"status": 200, "value": "Your work is much appreciated, thanks !"}

    :Allowed: Node
    :query task_id: Task's id (required)
    :query publish_uri: Revoked publication URI of the media asset (required)
    :query status: Task's status (SUCCESS) or error's details (required)
    :statuscode 200: OK
    :statuscode 400: Key ``key`` not found. *or* on type or value error
    :statuscode 401: Authenticate.
    :statuscode 403: Authentication Failed.
    :statuscode 404: No publication task with id ``id``.
    :statuscode 404: Unable to find media asset with id ``id``.
    :statuscode 415: Requires (valid) json content-type.
    """
    try:
        requires_auth(request=request, allow_node=True)
        data = get_request_data(request, qs_only_first_value=True)
        task_id = data[u'task_id']
        publish_uri = data[u'publish_uri'] if u'publish_uri' in data else None
        status = data[u'status']
        logging.debug(u'task {0}, revoked publish_uri {1}, status {2}'.format(task_id, publish_uri, status))
        orchestra.publisher_revoke_callback(task_id, publish_uri, status)
        return ok_200(u'Your work is much appreciated, thanks !', False)
    except Exception as e:
        map_exceptions(e)

# Main -----------------------------------------------------------------------------------------------------------------

if __name__ == u'__main__':

    from library.oscied_lib.pyutils.py_unicode import configure_unicode
    configure_unicode()

    try:
        config = OrchestraLocalConfig.read(u'local_config.pkl')
        setup_logging(filename=u'orchestra.log', console=True, level=config.log_level)
        logging.info(u'OSCIED Orchestra by David Fischer 2013')
        logging.info(u'Configuration : {0}'.format(unicode(object2json(config, True))))

        if not config.storage_uri():
            logging.warning(u'Shared storage is not set in configuration ... exiting')
            sys.exit(0)

        if not config.mongo_admin_connection:
            logging.warning(u'MongoDB is not set in configuration ... mocking')

        if not config.rabbit_connection:
            logging.warning(u'RabbitMQ is not set in configuration ... exiting')
            sys.exit(0)

        orchestra = OrchestraAPICore(config)
        logging.info(u'Start REST API')
        #app.config['PROPAGATE_EXCEPTIONS'] = True
        app.run(host=u'0.0.0.0', debug=orchestra.config.verbose)

    except Exception as error:
        logging.exception(error)
        logging.exception(u'Orchestra ... exiting')
        sys.exit(1)
