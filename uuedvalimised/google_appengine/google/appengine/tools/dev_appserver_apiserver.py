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




"""Helper CGI for Apiserver in the development app server.

This is a fake apiserver proxy that does simple transforms on requests that
come in to /_ah/api and then re-dispatches them to /_ah/spi.  It does not do
any authentication, quota checking, DoS checking, etc.

In addition, the proxy loads api configs from
/_ah/spi/BackendService.getApiConfigs prior to making the first call to the
backend at /_ah/spi and afterwards if app.yaml is changed.
"""

from __future__ import with_statement




import cgi
import cStringIO
import httplib
try:

  import json
except ImportError:

  import simplejson as json

import logging
import mimetools
import re


API_SERVING_PATTERN = '/_ah/api/.*'





SPI_ROOT_FORMAT = 'http://127.0.0.1:%s/_ah/spi/%s'


_API_REST_PATH_FORMAT = '{!name}/{!version}/%s'
_PATH_VARIABLE_PATTERN = r'[a-zA-Z_][a-zA-Z_\d]*'
_RESERVED_PATH_VARIABLE_PATTERN = r'!' + _PATH_VARIABLE_PATTERN
_PATH_VALUE_PATTERN = r'[^:/?#\[\]{}]*'


class ApiRequest(object):
  """Simple data object representing an API request.

  Takes an app_server CGI request and environment in the constructor.
  Parses the request into convenient pieces and stores them as members.
  """
  API_PREFIX = '/_ah/api/'

  def __init__(self, base_env_dict, dev_appserver, request=None):
    """Constructor.

    Args:
      base_env_dict: Dictionary of CGI environment parameters.
      dev_appserver: used to call standard SplitURL method.
      request: AppServerRequest.  Can be None.
    """
    self.cgi_env = base_env_dict
    self.headers = {}
    self.http_method = base_env_dict['REQUEST_METHOD']
    self.port = base_env_dict['SERVER_PORT']
    if request:
      self.path, self.query = dev_appserver.SplitURL(request.relative_url)


      self.body = request.infile.read()
      for header in request.headers.headers:
        header_name, header_value = header.split(':', 1)
        self.headers[header_name.strip()] = header_value.strip()
    else:
      self.body = ''
      self.path = self.API_PREFIX
      self.query = ''
    assert self.path.startswith(self.API_PREFIX)
    self.path = self.path[len(self.API_PREFIX):]
    self.parameters = cgi.parse_qs(self.query)
    self.body_obj = json.loads(self.body) if self.body else {}
    self.request_id = None

  def _IsRpc(self):








    return self.path == 'rpc'


class DiscoveryApiProxy(object):
  """Proxies discovery service requests to a known cloud endpoint."""



  _DISCOVERY_PROXY_HOST = 'webapis-discovery.appspot.com'
  _STATIC_PROXY_HOST = 'webapis-discovery.appspot.com'
  _DISCOVERY_API_PATH_PREFIX = '/_ah/api/discovery/v1/'

  def _DispatchRequest(self, path, body):
    """Proxies GET request to discovery service API.

    Args:
      path: URL path relative to discovery service.
      body: HTTP POST request body.

    Returns:
      HTTP response body or None if it failed.
    """
    full_path = self._DISCOVERY_API_PATH_PREFIX + path
    headers = {'Content-type': 'application/json'}
    connection = httplib.HTTPSConnection(self._DISCOVERY_PROXY_HOST)
    try:
      connection.request('POST', full_path, body, headers)
      response = connection.getresponse()
      response_body = response.read()
      if response.status != 200:
        logging.error('Discovery API proxy failed on %s with %d.\r\n'
                      'Request: %s\r\nResponse: %s',
                      full_path, response.status, body, response_body)
        return None
      return response_body
    finally:
      connection.close()

  def GenerateDiscoveryDoc(self, api_config, api_format):
    """Generates a discovery document from an API file.

    Args:
      api_config: .api file contents as string.
      api_format: 'rest' or 'rpc' depending on the which kind of discvoery doc.

    Returns:
      Discovery doc as JSON string.

    Raises:
      ValueError: When api_format is invalid.
    """
    if api_format not in ['rest', 'rpc']:
      raise ValueError('Invalid API format')
    path = 'apis/generate/' + api_format
    request_dict = {'config': json.dumps(api_config)}
    request_body = json.dumps(request_dict)
    return self._DispatchRequest(path, request_body)

  def GenerateDirectory(self, api_configs):
    """Generates an API directory from a list of API files.

    Args:
      api_configs: list of strings which are the .api file contents.

    Returns:
      API directory as JSON string.
    """
    request_dict = {'configs': api_configs}
    request_body = json.dumps(request_dict)
    return self._DispatchRequest('apis/generate/directory', request_body)

  def GetStaticFile(self, path):
    """Returns static content via a GET request.

    Args:
      path: URL path after the domain.

    Returns:
      Tuple of (response, response_body):
        response: HTTPResponse object.
        response_body: Response body as string.
    """
    connection = httplib.HTTPSConnection(self._STATIC_PROXY_HOST)
    try:
      connection.request('GET', path, None, {})
      response = connection.getresponse()
      response_body = response.read()
    finally:
      connection.close()
    return response, response_body


class DiscoveryService(object):
  """Implements the local devserver discovery service.

     This has a static minimal version of the discoverable part of the
     discovery .api file.
     It only handles returning the discovery doc and directory, and ignores
     directory parameters to filter the results.

     The discovery docs/directory are created by calling a cloud endpoint
     discovery service to generate the discovery docs/directory from an .api
     file/set of .api files.
  """

  _GET_REST_API = 'apisdev.getRest'
  _GET_RPC_API = 'apisdev.getRpc'
  _LIST_API = 'apisdev.list'
  API_CONFIG = {
      'name': 'discovery',
      'version': 'v1',
      'methods': {
          'discovery.apis.getRest': {
              'path': 'apis/{api}/{version}/rest',
              'httpMethod': 'GET',
              'rosyMethod': _GET_REST_API,
          },
          'discovery.apis.getRpc': {
              'path': 'apis/{api}/{version}/rpc',
              'httpMethod': 'GET',
              'rosyMethod': _GET_RPC_API,
          },
          'discovery.apis.list': {
              'path': 'apis',
              'httpMethod': 'GET',
              'rosyMethod': _LIST_API,
          },
      }
  }

  def __init__(self, config_manager, api_request, outfile):
    """Initializes an instance of the DiscoveryService.

    Args:
      config_manager: an instance of ApiConfigManager.
      api_request: an instance of ApiRequest.
      outfile: the CGI file object to write the response to.
    """
    self._config_manager = config_manager
    self._params = json.loads(api_request.body or '{}')
    self._outfile = outfile
    self._discovery_proxy = DiscoveryApiProxy()

  def _SendSuccessResponse(self, response):
    """Sends an HTTP 200 json success response.

    Args:
      response: Response body as string to return.

    Returns:
      Sends back an HTTP 200 json success response.
    """
    headers = {'Content-Type': 'application/json; charset=UTF-8'}
    return SendCGIResponse('200', headers, response, self._outfile)

  def _GetRpcOrRest(self, api_format):
    """Sends back HTTP response with API directory.

    Args:
      api_format: Either 'rest' or 'rpc'. Sends CGI response containing
        the discovery doc for the api/version.

    Returns:
      None.
    """
    api = self._params['api']
    version = self._params['version']
    lookup_key = (api, version)
    api_config = self._config_manager.configs.get(lookup_key)
    if not api_config:
      logging.warn('No discovery doc for version %s of api %s', version, api)
      SendCGINotFoundResponse(self._outfile)
      return
    doc = self._discovery_proxy.GenerateDiscoveryDoc(api_config, api_format)
    if not doc:
      error_msg = ('Failed to convert .api to discovery doc for '
                   'version %s of api %s') % (version, api)
      logging.error('%s', error_msg)
      SendCGIErrorResponse(error_msg, self._outfile)
      return
    self._SendSuccessResponse(doc)

  def _GetRest(self):
    return self._GetRpcOrRest('rest')

  def _GetRpc(self):
    return self._GetRpcOrRest('rpc')

  def _List(self):
    """Sends HTTP response containing the API directory."""
    api_configs = []
    for api_config in self._config_manager.configs.itervalues():



      if not api_config == self.API_CONFIG:
        api_configs.append(json.dumps(api_config))
    directory = self._discovery_proxy.GenerateDirectory(api_configs)
    if not directory:
      logging.error('Failed to get API directory')


      SendCGINotFoundResponse(self._outfile)
      return
    self._SendSuccessResponse(directory)

  def HandleDiscoveryRequest(self, path):
    """Returns the result of a discovery service request.

    Args:
      path: the SPI API path

    Returns:
      JSON string with result of discovery service API request.
    """
    if path == self._GET_REST_API:
      self._GetRest()
    elif path == self._GET_RPC_API:
      self._GetRpc()
    elif path == self._LIST_API:
      self._List()
    else:
      return False
    return True


class ApiConfigManager(object):
  """Manages loading api configs and method lookup."""

  def __init__(self):
    self._rpc_method_dict = {}
    self._rest_methods = []
    self.configs = {}

  @staticmethod
  def HasSpiEndpoint(config):
    """Checks if an SPI is registered with this App.

    Args:
      config: Parsed app.yaml as an appinfo proto.

    Returns:
      True if any handler is registered for (/_ah/spi/.*).
    """
    return any(h.url.startswith('/_ah/spi/') for h in config.handlers)

  def _AddDiscoveryConfig(self):
    lookup_key = (DiscoveryService.API_CONFIG['name'],
                  DiscoveryService.API_CONFIG['version'])
    self.configs[lookup_key] = DiscoveryService.API_CONFIG

  def ParseApiConfigResponse(self, body):
    """Parses a json api config and registers methods for dispatch.

    Side effects:
      Parses method name, etc for all methods and updates the indexing
      datastructures with the information.

    Args:
      body: body of getApiConfigs response
    """


    try:
      response_obj = json.loads(body)
    except ValueError, unused_err:
      logging.error('Can not parse BackendService.getApiConfigs response: %s',
                    body)
    else:
      self._AddDiscoveryConfig()
      for api_config_json in response_obj.get('items', []):
        try:
          config = json.loads(api_config_json)
        except ValueError, unused_err:
          logging.error('Can not parse API config: %s',
                        api_config_json)
        else:
          lookup_key = config.get('name', ''), config.get('version', '')
          self.configs[lookup_key] = config

      for config in self.configs.itervalues():
        version = config.get('version', '')
        for method_name, method in config.get('methods', {}).iteritems():
          self.SaveRpcMethod(method_name, version, method)
          self.SaveRestMethod(method_name, version, method)

  @staticmethod
  def CompilePathPattern(pattern):
    """Generates a compiled regex pattern for a path pattern.

    e.g. '/{!name}/{!version}/notes/{id}'
    returns re.compile(r'/([^:/?#\[\]{}]*)'
                       r'/([^:/?#\[\]{}]*)'
                       r'/notes/(?P<id>[^:/?#\[\]{}]*)')
    Note in this example that !name and !version are reserved variable names
    used to match the API name and version that should not be migrated into the
    method argument namespace.  As such they are not named in the regex, so
    groupdict() excludes them.

    Args:
      pattern: parameterized path pattern to be checked

    Returns:
      compiled regex to match this path pattern
    """

    def ReplaceReservedVariable(match):
      """Replaces a {!variable} with a regex to match it not by name.

      Args:
        match: The matching regex group as sent by re.sub()

      Returns:
        Regex to match the variable by name, if the full pattern was matched.
      """
      if match.lastindex > 1:
        return '%s(%s)' % (match.group(1), _PATH_VALUE_PATTERN)
      return match.group(0)

    def ReplaceVariable(match):
      """Replaces a {variable} with a regex to match it by name.

      Args:
        match: The matching regex group as sent by re.sub()

      Returns:
        Regex to match the variable by name, if the full pattern was matched.
      """
      if match.lastindex > 1:
        return '%s(?P<%s>%s)' % (match.group(1), match.group(2),
                                 _PATH_VALUE_PATTERN)
      return match.group(0)




    pattern = re.sub('(/|^){(%s)}(?=/|$)' % _RESERVED_PATH_VARIABLE_PATTERN,
                     ReplaceReservedVariable, pattern, 2)
    pattern = re.sub('(/|^){(%s)}(?=/|$)' % _PATH_VARIABLE_PATTERN,
                     ReplaceVariable, pattern)
    return re.compile(pattern + '/?$')

  def SaveRpcMethod(self, method_name, version, method):
    """Store JsonRpc api methods in a map for lookup at call time.

    (rpcMethodName, apiVersion) => method.

    Args:
      method_name: Name of the API method
      version: Version of the API
      method: method descriptor (as in the api config file).
    """
    self._rpc_method_dict[(method_name, version)] = method

  def LookupRpcMethod(self, method_name, version):
    """Lookup the JsonRPC method at call time.

    The method is looked up in self._rpc_method_dict, the dictionary that
    it is saved in for SaveRpcMethod().

    Args:
      method_name: String name of the method
      version: String version of the API

    Returns:
      Method descriptor as specified in the API configuration.
    """
    method = self._rpc_method_dict.get((method_name, version))
    return method

  def SaveRestMethod(self, method_name, version, method):
    """Store Rest api methods in a list for lookup at call time.

    The list is self._rest_methods, a list of tuples:
      [(<compiled_path>, <path_pattern>, <method_dict>), ...]
    where:
      <compiled_path> is a compiled regex to match against the incoming URL
      <path_pattern> is a string representing the original path pattern,
        checked on insertion to prevent duplicates.     -and-
      <method_dict> is a dict (httpMethod, apiVersion) => (method_name, method)

    This structure is a bit complex, it supports use in two contexts:
      Creation time:
        - SaveRestMethod is called repeatedly, each method will have a path,
          which we want to be compiled for fast lookup at call time
        - We want to prevent duplicate incoming path patterns, so store the
          un-compiled path, not counting on a compiled regex being a stable
          comparison as it is not documented as being stable for this use.
        - Need to store the method that will be mapped at calltime.
        - Different methods may have the same path but different http method.
          and/or API versions.
      Call time:
        - Quickly scan through the list attempting .match(path) on each
          compiled regex to find the path that matches.
        - When a path is matched, look up the API version and method from the
          request and get the method name and method config for the matching
          API method and method name.

    Args:
      method_name: Name of the API method
      version: Version of the API
      method: method descriptor (as in the api config file).
    """
    path_pattern = _API_REST_PATH_FORMAT % method.get('path', '')
    http_method = method.get('httpMethod', '').lower()
    for _, path, methods in self._rest_methods:
      if path == path_pattern:
        methods[(http_method, version)] = method_name, method
        break
    else:
      self._rest_methods.append(
          (self.CompilePathPattern(path_pattern),
           path_pattern,
           {(http_method, version): (method_name, method)}))

  def LookupRestMethod(self, path, http_method):
    """Look up the rest method at call time.

    The method is looked up in self._rest_methods, the list it is saved
    in for SaveRestMethod.

    Args:
      path: Path from the URL of the request.
      http_method: HTTP method of the request.

    Returns:
      Tuple of (<method name>, <method>, <params>)
      Where:
        <method name> is the string name of the method that was matched.
        <method> is the descriptor as specified in the API configuration. -and-
        <params> is a dict of path parameters matched in the rest request.
    """
    for compiled_path_pattern, unused_path, methods in self._rest_methods:
      match = compiled_path_pattern.match(path)
      if match:
        params = match.groupdict()
        version = match.group(2)
        method_key = (http_method.lower(), version)
        method_name, method = methods.get(method_key, (None, None))
        if method is not None:
          break
    else:
      logging.warn('No endpoint found for path: %s', path)
      method_name = None
      method = None
      params = None
    return method_name, method, params


def CreateApiserverDispatcher(config_manager=None):
  """Function to create Apiserver dispatcher.

  Args:
    config_manager: Allow setting of ApiConfigManager for testing.

  Returns:
    New dispatcher capable of handling requests to the built-in apiserver
    handlers.
  """



  from google.appengine.tools import dev_appserver

  class ApiserverDispatcher(dev_appserver.URLDispatcher):
    """Dispatcher that handles requests to the built-in apiserver handlers."""

    _API_EXPLORER_URL = 'https://developers.google.com/apis-explorer/?base='

    class RequestState(object):
      """Enum tracking request state."""
      INIT = 0
      GET_API_CONFIGS = 1
      SPI_CALL = 2
      END = 3



    def __init__(self, config_manager=None, *args, **kwargs):
      self._is_rpc = None
      self._request_stage = self.RequestState.INIT
      self._is_batch = False
      if config_manager is None:
        config_manager = ApiConfigManager()
      self.config_manager = config_manager
      self._dispatchers = []
      self._AddDispatcher('/_ah/api/explorer/?$',
                          self.HandleApiExplorerRequest)
      self._AddDispatcher('/_ah/api/static/.*$',
                          self.HandleApiStaticRequest)
      dev_appserver.URLDispatcher.__init__(self, *args, **kwargs)

    def _AddDispatcher(self, path_regex, dispatch_function):
      """Add a request path and dispatch handler.

      Args:
        path_regex: Regex path to match against incoming requests.
        dispatch_function: Function to call for these requests.  The function
          should take (request, outfile, base_env_dict) as arguments and
          return True.
      """
      self._dispatchers.append((re.compile(path_regex), dispatch_function))

    def _EndRequest(self):
      """End the request and clean up.

      Sets the request state to END and cleans up any variables that
      need it.
      """
      self._request_stage = self.RequestState.END
      self._is_batch = False

    def IsRpc(self):
      """Check if the current request is an RPC request.

      This should only be used after Dispatch, where this info is cached.

      Returns:
        True if the current request is an RPC.  False if not.
      """
      assert self._is_rpc is not None
      return self._is_rpc

    def DispatchNonApiRequests(self, request, outfile, base_env_dict):
      """Dispatch this request if this is a request to a reserved URL.

      Args:
        request: AppServerRequest.
        outfile: The response file.
        base_env_dict: Dictionary of CGI environment parameters if available.
          Defaults to None.

      Returns:
        False if the request doesn't match one of the reserved URLs this
        handles.  True if it is handled.
      """
      for path_regex, dispatch_function in self._dispatchers:
        if path_regex.match(request.relative_url):
          return dispatch_function(request, outfile, base_env_dict)
      return False

    def Dispatch(self,
                 request,
                 outfile,
                 base_env_dict=None):
      """Handles dispatch to apiserver handlers.

      base_env_dict should contain at least:
      REQUEST_METHOD, REMOTE_ADDR, SERVER_SOFTWARE, SERVER_NAME,
      SERVER_PROTOCOL, SERVER_PORT

      Args:
        request: AppServerRequest.
        outfile: The response file.
        base_env_dict: Dictionary of CGI environment parameters if available.
          Defaults to None.

      Returns:
        AppServerRequest internal redirect for normal API calls or
        None for error conditions (e.g. method not found -> 404) and
        other calls not requiring the GetApiConfigs redirect.
      """
      if self._request_stage != self.RequestState.INIT:
        return self.FailRequest('Dispatch in unexpected state', outfile)

      if not base_env_dict:
        return self.FailRequest('CGI Environment Not Available', outfile)

      if self.DispatchNonApiRequests(request, outfile, base_env_dict):
        return None


      self.request = ApiRequest(base_env_dict, dev_appserver, request)





      self._is_rpc = self.request._IsRpc()


      self._request_stage = self.RequestState.GET_API_CONFIGS
      return self.GetApiConfigs(base_env_dict, dev_appserver)

    def HandleApiExplorerRequest(self, unused_request, outfile, base_env_dict):
      """Handler for requests to _ah/api/explorer.

      Args:
        unused_request: AppServerRequest.
        outfile: The response file.
        base_env_dict: Dictionary of CGI environment parameters
          if available. Defaults to None.

      Returns:
        True
        We will redirect these requests to the google apis explorer.
      """
      base_url = 'http://%s:%s/_ah/api' % (base_env_dict['SERVER_NAME'],
                                           base_env_dict['SERVER_PORT'])
      redirect_url = self._API_EXPLORER_URL + base_url
      SendCGIRedirectResponse(redirect_url, outfile)
      return True

    def HandleApiStaticRequest(self, request, outfile, unused_base_env_dict):
      """Handler for requests to _ah/api/static/.*.

      Args:
        request: AppServerRequest.
        outfile: The response file.
        unused_base_env_dict: Dictionary of CGI environment parameters
          if available. Defaults to None.

      Returns:
        True
        We will redirect these requests to an endpoint proxy.
      """
      discovery_api_proxy = DiscoveryApiProxy()
      response, body = discovery_api_proxy.GetStaticFile(request.relative_url)
      if response.status == 200:
        SendCGIResponse('200',
                        {'Content-Type': response.getheader('Content-Type')},
                        body, outfile)
      else:
        logging.error('Discovery API proxy failed on %s with %d. Details: %s',
                      request.relative_url, response.status, body)
        SendCGIResponse(response.status, dict(response.getheaders()), body,
                        outfile)
      return True

    def EndRedirect(self, dispatched_output, outfile):
      """Handle the end of getApiConfigs and SPI complete notification.

      This EndRedirect is called twice.

      The first time is upon completion of the BackendService.getApiConfigs()
      call.  After this call, the set of all available methods and their
      parameters / paths / config is contained in dispatched_output.  This is
      parsed and used to dispatch the request to the SPI backend itself.

      In order to cause a second dispatch and EndRedirect, this EndRedirect
      will return an AppServerRequest filled out with the SPI backend request.

      The second time it is called is upon completion of the call to the SPI
      backend. After this call, if the initial request (sent in Dispatch, prior
      to getApiConfigs) is used to reformat the response as needed.  This
      currently only results in changes for JsonRPC requests, where the response
      body is moved into {'result': response_body_goes_here} and the request id
      is copied back into the response.

      Args:
        dispatched_output: resulting output from the SPI
        outfile: final output file for this handler

      Returns:
        An AppServerRequest for redirect or None for an immediate response.
      """
      if self._request_stage == self.RequestState.GET_API_CONFIGS:
        if self.HandleGetApiConfigsResponse(dispatched_output, outfile):
          return self.CallSpi(outfile)
      elif self._request_stage == self.RequestState.SPI_CALL:
        return self.HandleSpiResponse(dispatched_output, outfile)
      else:
        return self.FailRequest('EndRedirect in unexpected state', outfile)

    def GetApiConfigs(self, cgi_env, dev_appserver):
      """Makes a call to BackendService.getApiConfigs and parses result.

      Args:
        cgi_env: CGI environment dictionary as passed in by the framework
        dev_appserver: dev_appserver instance used to generate AppServerRequest.

      Returns:
        AppServerRequest to be returned as an internal redirect to getApiConfigs
      """
      request = ApiRequest(cgi_env, dev_appserver)
      request.path = 'BackendService.getApiConfigs'
      request.body = '{}'
      return BuildCGIRequest(cgi_env, request, dev_appserver)

    @staticmethod
    def VerifyResponse(response, status_code, content_type=None):
      """Verifies that a response has the expected status and content type.

      Args:
        response: Response to be checked.
        status_code: HTTP status code to be compared with response status.
        content_type: acceptable Content-Type: header value, None allows any.

      Returns:
        True if both status_code and content_type match, else False.
      """
      if response.status_code != status_code:
        return False
      if content_type is None:
        return True
      for header in response.headers:
        if header.lower() == 'content-type':
          return response.headers[header].lower() == content_type
      else:
        return False

    @staticmethod
    def ParseCgiResponse(response):
      """Parses a CGI response, returning a headers dict and body.

      Args:
        response: a CGI response

      Returns:
        tuple of ({header: header_value, ...}, body)
      """
      header_dict = {}
      for header in response.headers.headers:
        header_name, header_value = header.split(':', 1)
        header_dict[header_name.strip()] = header_value.strip()

      if response.body:
        body = response.body.read()
      else:
        body = ''
      return header_dict, body

    def HandleGetApiConfigsResponse(self, dispatched_output, outfile):
      """Parses the result of getApiConfigs, returning True on success.

      Args:
        dispatched_output: Output from the getApiConfigs call handler.
        outfile: CGI output handle, used for error conditions.

      Returns:
        True on success, False on failure
      """
      response = dev_appserver.RewriteResponse(dispatched_output)
      if self.VerifyResponse(response, 200, 'application/json'):
        self.config_manager.ParseApiConfigResponse(response.body.read())
        return True
      else:
        self.FailRequest('BackendService.getApiConfigs Error', outfile)
        return False

    def CallSpi(self, outfile):
      """Generate SPI call (from earlier-saved request).

      Side effects:
        self.request is modified from Rest/JsonRPC format to apiserving format.

      Args:
        outfile: File to write out CGI-style response in case of error.

      Returns:
        AppServerRequest for redirect or None to send immediate CGI response.
      """
      if self.IsRpc():
        method_config = self.LookupRpcMethod()
        params = None
      else:
        method_config, params = self.LookupRestMethod()
      if method_config:
        self.TransformRequest(params, method_config)
        discovery_service = DiscoveryService(self.config_manager, self.request,
                                             outfile)

        if not discovery_service.HandleDiscoveryRequest(self.request.path):
          self._request_stage = self.RequestState.SPI_CALL
          return BuildCGIRequest(self.request.cgi_env, self.request,
                                 dev_appserver)
      else:
        self._EndRequest()
        return SendCGINotFoundResponse(outfile)

    def HandleSpiResponse(self, dispatched_output, outfile):
      """Handle SPI response, transforming output as needed.

      Args:
        dispatched_output: Response returned by SPI backend.
        outfile: File-like object to write transformed result.

      Returns:
        None
      """

      response = dev_appserver.AppServerResponse(
          response_file=dispatched_output)
      response_headers, body = self.ParseCgiResponse(response)



      headers = {}
      for header, value in response_headers.items():
        if (header.lower() == 'content-type' and
            not value.lower().startswith('application/json')):
          return self.FailRequest('Non-JSON reply: %s' % body, outfile)
        elif header.lower() not in ('content-length', 'content-type'):
          headers[header] = value

      if self.IsRpc():
        body = self.TransformJsonrpcResponse(body)
      self._EndRequest()
      return SendCGIResponse(response.status_code, headers, body, outfile)

    def FailRequest(self, message, outfile):
      """Write an immediate failure response to outfile, no redirect.

      Args:
        message: Error message to be displayed to user (plain text).
        outfile: File-like object to write CGI response to.

      Returns:
        None
      """
      self._EndRequest()
      return SendCGIErrorResponse(message, outfile)

    def LookupRestMethod(self):
      """Looks up and returns rest method for the currently-pending request.

      This method uses self.request as the currently-pending request.

      Returns:
        tuple of (method, parameters)
      """
      method_name, method, params = self.config_manager.LookupRestMethod(
          self.request.path, self.request.http_method)
      self.request.method_name = method_name
      return method, params

    def LookupRpcMethod(self):
      """Looks up and returns RPC method for the currently-pending request.

      This method uses self.request as the currently-pending request.

      Returns:
        RPC method that was found for the current request.
      """
      if not self.request.body_obj:
        return None
      try:
        method_name = self.request.body_obj.get('method', '')
      except AttributeError:




        if len(self.request.body_obj) != 1:
          raise NotImplementedError('Batch requests with more than 1 element '
                                    'not supported in dev_appserver.  Found '
                                    '%d elements.' % len(self.request.body_obj))
        logging.info('Converting batch request to single request.')
        self.request.body_obj = self.request.body_obj[0]
        method_name = self.request.body_obj.get('method', '')
        self._is_batch = True

      version = self.request.body_obj.get('apiVersion', '')
      self.request.method_name = method_name
      return self.config_manager.LookupRpcMethod(method_name, version)

    def TransformRequest(self, params, method_config):
      """Transforms self.request to apiserving request.

      This method uses self.request to determine the currently-pending request.
      This method accepts a rest-style or RPC-style request.

      Side effects:
        Updates self.request to apiserving format. (e.g. updating path to be the
        method name, and moving request parameters to the body.)

      Args:
        params: Path parameters dictionary for rest request
        method_config: API config of the method to be called
      """
      if self.IsRpc():
        self.TransformJsonrpcRequest()
      else:
        self.TransformRestRequest(params)
      self.request.path = method_config.get('rosyMethod', '')

    def TransformRestRequest(self, params):
      """Translates a Rest request/response into an apiserving request/response.

      Side effects:
        Updates self.request to apiserving format. (e.g. updating path to be the
        method name, and moving request parameters to the body.)

      Args:
        params: URL path parameter dict extracted by config_manager lookup.
      """
      body_obj = json.loads(self.request.body or '{}')
      if params:
        body_obj.update(params)
      if self.request.parameters:
        body_obj.update(self.request.parameters)
      self.request.body = json.dumps(body_obj)

    def TransformJsonrpcRequest(self):
      """Translates a JsonRpc request/response into apiserving request/response.

      Side effects:
        Updates self.request to apiserving format. (e.g. updating path to be the
        method name, and moving request parameters to the body.)
      """
      body_obj = json.loads(self.request.body) if self.request.body else {}
      try:
        self.request.request_id = body_obj.get('id')
      except AttributeError:




        assert self._is_batch
        if len(body_obj) != 1:
          raise NotImplementedError('Batch requests with more than 1 element '
                                    'not supported in dev_appserver.  Found '
                                    '%d elements.' % len(self.request.body_obj))
        body_obj = body_obj[0]
        self.request.request_id = body_obj.get('id')
      body_obj = body_obj.get('params', {})
      self.request.body = json.dumps(body_obj)

    def TransformJsonrpcResponse(self, response_body):
      """Translates a apiserving response to a JsonRpc response.

      Side effects:
        Updates self.request to JsonRpc format. (e.g. restoring request id
        and moving body object into {'result': body_obj}

      Args:
        response_body: Backend response to transform back to JsonRPC

      Returns:
        Updated, JsonRPC-formatted request body
      """
      body_obj = {'result': json.loads(response_body)}
      if self.request.request_id is not None:
        body_obj['id'] = self.request.request_id
      if self._is_batch:
        body_obj = [body_obj]
      return json.dumps(body_obj)

  return ApiserverDispatcher(config_manager)


def BuildCGIRequest(base_env_dict, request, dev_appserver):
  """Build a CGI request to Call a method on an SPI backend.

  Args:
    base_env_dict: CGI environment dict
    request: ApiRequest to be converted to a CGI request
    dev_appserver: Handle to dev_appserver to generate CGI request.

  Returns:
    dev_appserver.AppServerRequest internal redirect object
  """
  if request.headers is None:
    request.headers = {}


  request.headers['Content-Type'] = 'application/json'
  url = SPI_ROOT_FORMAT % (request.port, request.path)
  base_env_dict['REQUEST_METHOD'] = 'POST'






  header_outfile = cStringIO.StringIO()
  body_outfile = cStringIO.StringIO()
  WriteHeaders(request.headers, header_outfile, len(request.body))
  body_outfile.write(request.body)
  header_outfile.seek(0)
  body_outfile.seek(0)
  return dev_appserver.AppServerRequest(
      url, None, mimetools.Message(header_outfile), body_outfile)


def WriteHeaders(headers, outfile, content_len=None):
  """Write headers to the output file, updating content length if needed.

  Args:
    headers: Header dict to be written
    outfile: File-like object to send headers to
    content_len: Optional updated content length to update content-length with
  """
  wrote_content_length = False
  for header, value in headers.iteritems():
    if header.lower() == 'content-length' and content_len is not None:
      value = content_len
      wrote_content_length = True
    outfile.write('%s: %s\r\n' % (header, value))
  if not wrote_content_length and content_len:
    outfile.write('Content-Length: %s\r\n' % content_len)


def SendCGINotFoundResponse(outfile):
  SendCGIResponse('404', {'Content-Type': 'text/plain'}, 'Not Found', outfile)


def SendCGIErrorResponse(message, outfile):
  body = json.dumps({'error': {'message': message}})
  SendCGIResponse('500', {'Content-Type': 'application/json'}, body, outfile)


def SendCGIRedirectResponse(redirect_location, outfile):
  SendCGIResponse('302', {'Location': redirect_location}, None, outfile)


def SendCGIResponse(status, headers, content, outfile):
  """Dump reformatted response to CGI outfile.

  Args:
    status: HTTP status code to send
    headers: Headers dictionary {header_name: header_value, ...}
    content: Body content to write
    outfile: File-like object where response will be written.

  Returns:
    None
  """
  outfile.write('Status: %s\r\n' % status)
  WriteHeaders(headers, outfile, len(content) if content else None)
  outfile.write('\r\n')
  if content:
    outfile.write(content)
  outfile.seek(0)
