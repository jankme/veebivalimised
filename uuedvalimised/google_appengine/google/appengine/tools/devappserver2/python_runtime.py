#!/usr/bin/env python
#
# Copyright 2007 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
"""Serves content for "script" handlers using the Python runtime."""


import os
import sys

import google
from google.appengine.api import appinfo
from google.appengine.tools.devappserver2 import http_runtime
from google.appengine.tools.devappserver2 import instance

_RUNTIME_PATH = (
    os.path.join(os.path.dirname(sys.argv[0]), '_python_runtime.py'))


class PythonRuntimeInstanceFactory(instance.InstanceFactory):
  """A factory that creates new Python runtime Instances."""

  START_URL_MAP = appinfo.URLMap(
      url='/_ah/start',
      script='$PYTHON_LIB/default_start_handler.py',
      login='admin')
  WARMUP_URL_MAP = appinfo.URLMap(
      url='/_ah/warmup',
      script='$PYTHON_LIB/default_warmup_handler.py',
      login='admin')
  SUPPORTS_INTERACTIVE_REQUESTS = True

  def __init__(self, request_data, runtime_config_getter, server_configuration):
    """Initializer for PythonRuntimeInstanceFactory.

    Args:
      request_data: A wsgi_request_info.WSGIRequestInfo that will be provided
          with request information for use by API stubs.
      runtime_config_getter: A function that can be called without arguments
          and returns the runtime_config_pb2.Config containing the configuration
          for the runtime.
      server_configuration: An application_configuration.ServerConfiguration
          instance respresenting the configuration of the server that owns the
          runtime.
    """
    super(PythonRuntimeInstanceFactory, self).__init__(
        request_data,
        8 if runtime_config_getter().threadsafe else 1, 10)
    self._runtime_config_getter = runtime_config_getter
    self._server_configuration = server_configuration

  def new_instance(self, instance_id, expect_ready_request=False):
    """Create and return a new Instance.

    Args:
      instance_id: A string or integer representing the unique (per server) id
          of the instance.
      expect_ready_request: If True then the instance will be sent a special
          request (i.e. /_ah/warmup or /_ah/start) before it can handle external
          requests.

    Returns:
      The newly created instance.Instance.
    """
    proxy = http_runtime.HttpRuntimeProxy(
        [sys.executable, _RUNTIME_PATH],
        self._runtime_config_getter,
        self._server_configuration,
        env=dict(os.environ, PYTHONHASHSEED='random'))
    return instance.Instance(self.request_data,
                             instance_id,
                             proxy,
                             self.max_concurrent_requests,
                             self.max_background_threads,
                             expect_ready_request)
