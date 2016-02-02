#!/usr/bin/env python

import yaml

from intmaniac.testset import Testset
from intmaniac import tools
from intmaniac.output import init_output

import sys
from os.path import join
from errno import *
from argparse import ArgumentParser

config = None
logger = None
derived_basedir = None
global_overrides = None


##############################################################################
#                                                                            #
# default configuration values for test config                               #
#                                                                            #
##############################################################################


##############################################################################
#                                                                            #
# reading of config data                                                     #
# initialization of test set objects                                         #
#                                                                            #
##############################################################################


def _get_test_set_groups(setupdata):
    """Always returns a list of list of Testsets
        :param setupdata the full yaml setup data
    """
    test_set_groups = setupdata['testsets']
    global_config = setupdata['global']
    step = 0
    rv = []
    # if it's not a list, just wrap it into one.
    if type(test_set_groups) == dict:
        test_set_groups = [test_set_groups]
    for tsgroup in test_set_groups:
        tsgroup_list = []
        rv.append(tsgroup_list)
        # this must be dict now
        for tsname in sorted(tsgroup.keys()):
            # makes for predictable order for testing ...
            tests = tsgroup[tsname]
            tsname = "%02d-%s" % (step, tsname) \
                if len(test_set_groups) > 1 \
                else tsname
            ts = Testset(name=tsname)
            tsgroup_list.append(ts)
            # remove global settings from test set
            tset_globals = tests.pop("_global") if "_global" in tests else {}
            for test_name, test_config in tests.items():
                test_config = tools.deep_merge(
                    global_config,
                    tset_globals,
                    test_config,
                    global_overrides
                )
                ts.add_from_config(test_name, test_config)
        step += 1
    return rv


def _get_setupdata():
    stub = tools.get_full_stub()
    filedata = None
    try:
        with open(config.config_file, "r") as ifile:
            filedata = yaml.safe_load(ifile)
    except IOError as e:
        # FileNotFoundError is python3 only. yihah.
        if e.errno == ENOENT:
            tools.fail("Could not find configuration file: %s" % config.config_file)
        else:
            tools.fail("Unspecified IO error: %s" % str(e))
    logger.info("Read configuration file %s" % config.config_file)
    return tools.deep_merge(stub, filedata)


def _prepare_overrides():
    global global_overrides
    global_overrides = tools.get_test_stub()
    # add config file entry
    global_overrides['meta']['_configfile'] = config.config_file
    # add test_basedir entry
    global_overrides['meta']['test_basedir'] = derived_basedir
    # add env settings from command line
    for tmp in config.env:
        try:
            k, v = tmp.split("=", 1)
            global_overrides['environment'][k] = v
        except ValueError:
            tools.fail("Invalid environment setting: %s" % tmp)


def _get_and_init_configuration():
    setupdata = _get_setupdata()
    _prepare_overrides()
    if "output_format" in setupdata:
        logger.warning("Text output format: %s" % setupdata['output_format'])
        init_output(setupdata['output_format'])
    return setupdata


##############################################################################
#                                                                            #
# run test sets logic                                                        #
#                                                                            #
##############################################################################


def _run_test_set_groups(tsgs):
    retval = True
    dumps = []
    for testsetgroup in tsgs:
        if not retval:
            # just for nicer output
            for tso in testsetgroup:
                logger.warning("skipping %s because of failed dependency" % tso)
            continue
        # everything in here is run in parallel
        for testsetobj in testsetgroup:
            testsetobj.start()
        for testsetobj in testsetgroup:
            testsetobj.join()
            retval = testsetobj.succeeded() and retval
            dumps.append(testsetobj.dump)
            if not testsetobj.succeeded():
                logger.critical("%s failed, skipping following testsets"
                             % testsetobj)
    print("TEST PROTOCOL")
    for dump_function in dumps:
        dump_function()
    return retval


##############################################################################
#                                                                            #
# startup initialization                                                     #
#                                                                            #
##############################################################################


def _prepare_environment(arguments):
    global config, logger, derived_basedir
    parser = ArgumentParser()
    parser.add_argument("-c", "--config-file",
                        help="specify configuration file",
                        default="./intmaniac.yaml")
    parser.add_argument("-e", "--env",
                        help="dynamically add a value to the environment",
                        default=[],
                        action="append")
    parser.add_argument("-v", "--verbose",
                        help="increase verbosity level, use multiple times",
                        default=0,
                        action="count")
    parser.add_argument("-t", "--temp-output-dir",
                        help="test dir location, default: $pwd/intmaniac")
    config = parser.parse_args(arguments)
    tools.init_logging(config)
    derived_basedir = tools.setup_up_test_directory(config)
    logger = tools.get_logger(__name__,
                              filename=join(derived_basedir, "root.log"))


def console_entrypoint():
    _prepare_environment(sys.argv[1:])
    configuration = _get_and_init_configuration()
    result = _run_test_set_groups(_get_test_set_groups(configuration))
    if not result:
        sys.exit(1)


if __name__ == "__main__":
    console_entrypoint()
