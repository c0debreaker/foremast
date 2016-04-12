"""Create Pipelines for Spinnaker"""
import argparse
import configparser
import json
import logging
import os

import murl
import requests
from jinja2 import Environment, FileSystemLoader
from tryagain import retries


class SpinnakerAppNotFound(Exception):
    pass


class SpinnakerApplicationListError(Exception):
    pass


class SpinnakerPipelineCreationFailed(Exception):
    pass


class SpinnakerPipeline:
    """Manipulate Spinnaker Pipelines.

    Args:
        app_name: Str of application name.
    """

    def __init__(self, app_info):
        self.log = logging.getLogger(__name__)

        self.here = os.path.dirname(os.path.realpath(__file__))
        self.config = self.get_configs()
        self.gate_url = self.config['spinnaker']['gate_url']
        self.app_name = self.app_exists(app_name=app_info['app'])
        self.app_info = app_info
        self.settings = self.get_settings()

        self.header = {'content-type': 'application/json'}

    def get_settings(self):
        with open('../raw.properties.json') as data_file:
            data = json.load(data_file)
        return data

    def get_configs(self):
        """Get main configuration.

        Returns:
            configparser.ConfigParser object with configuration loaded.
        """
        config = configparser.ConfigParser()
        configpath = "{}/../../configs/spinnaker.conf".format(self.here)
        config.read(configpath)

        self.log.debug('Configuration sections found: %s', config.sections())
        return config

    def get_template(self, template_name='', template_dict=None):
        """Get Jinja2 Template _template_name_.

        Args:
            template_name: Str of template name to retrieve.
            template_dict: Dict to use for template rendering.

        Returns:
            Dict of rendered JSON to send to Spinnaker.
        """
        templatedir = "{}/../../templates".format(self.here)
        jinja_env = Environment(loader=FileSystemLoader(templatedir))
        template = jinja_env.get_template(template_name)

        rendered_json = json.loads(template.render(**template_dict))
        self.log.debug('Rendered template: %s', rendered_json)
        return rendered_json

    def create_pipeline(self):
        """Sends a POST to spinnaker to create a new security group."""
        url = "{0}/pipelines".format(self.gate_url)

        previous_env = None
        self.log.debug('Envs: %s', self.settings['pipeline']['env'])
        for env in self.settings['pipeline']['env']:
            # Assume order of environments is correct
            self.app_info[env] = self.settings[env]

            self.log.debug('App info:\n%s', self.app_info)

            previous_env = env
            if previous_env:
                # use pipeline template
                template_name = 'pipeline_pipelinetrigger_template.json.j2'
                self.app_info[env].update({'pipeline_id': 'xxxxxxxxx'})
            else:
                # use template that uses jenkins
                template_name = 'pipeline_template.json'

            # temporary hack
            data = self.app_info[env]
            data['app']['appname'] = self.app_info[env]['app']

            pipeline_json = self.get_template(template_name=template_name,
                                              template_dict=data, )

            self.log.debug('Pipeline JSON:\n%s', pipeline_json)

            r = requests.post(url,
                              data=json.dumps(pipeline_json),
                              headers=self.header)

            if not r.ok:
                logging.error('Failed to create pipeline: %s', r.text)
                raise SpinnakerPipelineCreationFailed(r.json())

            logging.info('Successfully created %s pipeline', self.app_name)

        return True

    def get_apps(self):
        """Gets all applications from spinnaker."""
        url = '{0}/applications'.format(self.gate_url)
        r = requests.get(url)
        if r.ok:
            return r.json()
        else:
            logging.error(r.text)
            raise SpinnakerApplicationListError(r.text)

    def app_exists(self, app_name):
        """Checks to see if application already exists.

        Args:
            app_name: Str of application name to check.

        Returns:
            Str of application name

        Raises:
            SpinnakerAppNotFound
        """

        apps = self.get_apps()
        app_name = app_name.lower()
        for app in apps:
            if app['name'].lower() == app_name:
                logging.info('Application %s found!', app_name)
                return app_name

        logging.info('Application %s does not exist ... exiting', app_name)
        raise SpinnakerAppNotFound('Application "{0}" not found.'.format(
            app_name))

    def get_pipe_id(self, name=''):
        """Get the ID for Pipeline _name_.

        Args:
            name (str): Name of Pipeline to get ID for.

        Returns:
            str: ID of specified Pipeline.
            None: Pipeline or Spinnake Appliation not found.
        """
        return_id = None

        url = murl.Url(self.gate_url)
        url.path = 'applications/{app}/pipelineConfigs'.format(**self.app_info)
        response = requests.get(url.url)

        if response.ok:
            pipe_configs = response.json()

            for pipeline in pipe_configs:
                self.log.info('ID of %(name)s: %(id)s', pipeline)

                if pipeline['name'] == name:
                    return_id = pipeline['id']

        return return_id

    @retries(max_attempts=10, wait=10.0, exceptions=Exception)
    def check_task(self, taskid):

        try:
            taskurl = taskid.get('ref', '0000')
        except AttributeError:
            taskurl = taskid

        taskid = taskurl.split('/tasks/')[-1]

        self.log.info('Checking taskid %s' % taskid)

        url = '{0}/applications/{1}/tasks/{2}'.format(self.gate_url,
                                                      self.app_name,
                                                      taskid, )

        r = requests.get(url, headers=self.header)

        self.log.debug(r.json())
        if not r.ok:
            raise Exception
        else:
            json = r.json()

            status = json['status']

            self.log.info('Current task status: %s', status)
            STATUSES = ('SUCCEEDED', 'TERMINAL')

            if status in STATUSES:
                return status
            else:
                raise Exception


def main():
    """Run newer stuffs."""
    logging.basicConfig(format='%(asctime)s %(message)s')
    log = logging.getLogger(__name__)

    parser = argparse.ArgumentParser()
    parser.add_argument('-d',
                        '--debug',
                        action='store_true',
                        help='DEBUG output')
    parser.add_argument("--app",
                        help="The application name to create",
                        required=True)
    parser.add_argument("--region",
                        help="The region to create the security group",
                        required=True)
    parser.add_argument("--vpc",
                        help="The vpc to create the security group",
                        required=True)
    parser.add_argument("--triggerjob",
                        help="The job to monitor for pipeline triggering",
                        required=True)
    args = parser.parse_args()

    if args.debug:
        log.setLevel(logging.DEBUG)

    log.debug('Parsed arguments: %s', args)

    # Dictionary containing application info. This is passed to the class for processing
    appinfo = {
        'app': args.app,
        'vpc': args.vpc,
        'region': args.region,
        'triggerjob': args.triggerjob
    }

    spinnakerapps = SpinnakerPipeline(app_info=appinfo)
    spinnakerapps.create_pipeline()


if __name__ == "__main__":
    main()
