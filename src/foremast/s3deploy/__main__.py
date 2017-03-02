#   Foremast - Pipeline Tooling
#
#   Copyright 2016 Gogo, LLC
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

"""Sets up S3 deployment infrastructure.

Help: ``python -m src.foremast.s3 -h``
"""

import argparse
import logging

from ..args import add_app, add_debug, add_env, add_properties, add_region
from ..consts import LOGGING_FORMAT
from .s3deployments import S3Deployments

LOG = logging.getLogger(__name__)


def main():
    """setups s3 deployment infrastructure"""
    logging.basicConfig(format=LOGGING_FORMAT)

    parser = argparse.ArgumentParser(description=main.__doc__)
    add_debug(parser)
    add_app(parser)
    add_env(parser)
    add_properties(parser)
    add_region(parser)
    args = parser.parse_args()

    logging.getLogger(__package__.split('.')[0]).setLevel(args.debug)

    LOG.debug('Args: %s', vars(args))

    s3deploy = S3Deployments(app=args.app,
                             env=args.env,
                             region=args.region,
                             prop_path=args.properties
                             )
    s3deploy.create_bucket()


if __name__ == '__main__':
    main()