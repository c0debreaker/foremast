import base64
import logging
import os
import zipfile

import boto3

from ..exceptions import RequiredKeyNotFound
from ..utils import (get_role_arn, get_properties, get_details, get_subnets, get_security_group_id)

LOG = logging.getLogger(__name__)


class LambdaFunction(object):
    """Manipulate Lambda function"""

    def __init__(self, app, env, region, prop_path):
        """
        Lambda function object
        Args:
            app (str): Application name
            env (str): Environment/Account
            region (str): AWS Region
            prop_path (dict): Path of environment property file
        """
        self.app_name = app
        self.env = env
        self.region = region
        self.properties = get_properties(prop_path)
        generated = get_details(app=self.app_name)

        try:
            self.pipeline = self.properties['pipeline']['lambda']
        except KeyError:
            raise RequiredKeyNotFound("Lambda key in pipeline.json is required.")

        self.runtime = self.pipeline['runtime']
        self.description = self.pipeline['app_description']
        self.handler = self.pipeline['handler']
        self.vpc_enabled = self.pipeline['vpc_enabled']

        self.memory = self.properties[env]['app']['lambda_memory']
        self.timeout = self.properties[env]['app']['lambda_timeout']

        self.role_arn = get_role_arn(generated.iam()['role'], self.env, self.region)

        session = boto3.Session(profile_name=self.env, region_name=self.region)
        self.lambda_client = session.client('lambda')

    def _check_lambda(self):
        """Checks if lambda function exists
        Returns:
            True if function does exist
            False if function does not exist
        """
        exists = False
        try:
            self.lambda_client.get_function(FunctionName=self.app_name)
            exists = True
        except boto3.exceptions.botocore.exceptions.ClientError:
            pass
        return exists

    def _vpc_config(self):
        """Gets VPC config"""
        if self.vpc_enabled:
            subnets = get_subnets(env=self.env, region=self.region,
                                purpose='internal')['subnet_ids'][self.region]
            security_groups = self._get_sg_ids()

            vpc_config = {'SubnetIds': subnets, 'SecurityGroupIds': security_groups}
        else:
            vpc_config = {'SubnetIds': [], 'SecurityGroupIds': []}
        LOG.debug("Lambda VPC config setup: %s", vpc_config)
        return vpc_config


    def _get_sg_ids(self):
        """get IDs for all defined security groups

        Returns:
            list: security group IDs for all lambda_extras
        """
        try:
            lambda_extras = self.properties[self.env]['security_groups']['lambda_extras']
        except KeyError:
            lambda_extras = []

        security_groups = [self.app_name] + lambda_extras
        sg_ids = []
        for sg in security_groups:
            sg_id = get_security_group_id(name=sg, env=self.env, region=self.region)
            sg_ids.append(sg_id)
        return sg_ids

    def update_function_configuration(self, vpc_config):
        """Updates existing Lambda function configuration

        Args:
            vpc_config (dict): Dictionary of SubnetIds and SecurityGroupsIds for using
                               a VPC in lambda
        """

        self.lambda_client.update_function_configuration(FunctionName=self.app_name,
                                                         Runtime=self.runtime,
                                                         Role=self.role_arn,
                                                         Handler=self.handler,
                                                         Description=self.description,
                                                         Timeout=int(self.timeout),
                                                         MemorySize=int(self.memory),
                                                         VpcConfig=vpc_config)

        LOG.info("Successfully updated Lambda function")

    def create_function(self, vpc_config):
        """Creates lambda function, configures lambda parameters
        Args:
            vpc_config (dict): Dictionary of SubnetIds and SecurityGroupsIds for using
                               a VPC in lambda
        """

        # We need to upload non-zero zip when creating function
        # uploading hello_world python lambda function since AWS
        # doesn't care which executable is in ZIP
        zip_file = 'lambda-holder.zip'
        with zipfile.ZipFile(zip_file, mode='w') as z:
            z.writestr('index.py', 'print "Hello world"')

        contents = ''
        with open('lambda-holder.zip', 'rb') as openfile:
            contents = openfile.read()


        self.lambda_client.create_function(FunctionName=self.app_name,
                                           Runtime=self.runtime,
                                           Role=self.role_arn,
                                           Handler=self.handler,
                                           Code={
                                               'ZipFile': contents
                                           },
                                           Description=self.description,
                                           Timeout=int(self.timeout),
                                           MemorySize=int(self.memory),
                                           Publish=False,
                                           VpcConfig=vpc_config)

        LOG.info("Successfully created Lambda function")

    def create_lambda_function(self):
        """Creates or updates Lambda function"""
        vpc_config = self._vpc_config()
        if self._check_lambda():
            self.update_function_configuration(vpc_config)
        else:
            self.create_function(vpc_config)