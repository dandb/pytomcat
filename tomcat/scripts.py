#!/usr/bin/env python

import logging
from optparse import OptionParser, OptionGroup
from . import Tomcat, TomcatError, TomcatCluster
from deployer import ClusterDeployer, parse_warfiles

VERSION = "1.0"

conn_options = [ 'host', 'port', 'user', 'passwd' ]

def setup_logging(level, module='pytomcat',
                  fmt='%(asctime)s %(levelname)s %(message)s'):
    log = logging.getLogger(module)
    ch = logging.StreamHandler()
    formatter = logging.Formatter(fmt=fmt)
    ch.setFormatter(formatter)
    log.addHandler(ch)
    log.setLevel(level)

def create_option_parser(usage, epilog=None):
    err_choices = [ 'ERROR', 'WARN', 'INFO', 'DEBUG' ]
    parser = OptionParser(usage=usage, version="%prog " + VERSION,
                          add_help_option=False, epilog=epilog)
    parser.remove_option("--version")
    group = OptionGroup(parser, "General Options")
    group.add_option("-h", "--host", help="Tomcat server host",
                     default='localhost', dest='host')
    group.add_option("-P", "--port", help="Tomcat server port",
                     default='8080', dest='port')
    group.add_option("-u", "--user", help="Tomcat server username",
                     default='admin', dest='user')
    group.add_option("-p", "--password", help="Tomcat server password",
                     default='admin', dest='passwd')
    group.add_option("--loglevel", help="Log level ({0})".format(', '.join(err_choices)),
                     type="string", action="callback", metavar='LEVEL',
                     callback=lambda a, b, v, o: setup_logging(v))
    group.add_option("--help", help="show this help message and exit",
                     action="help")
    group.add_option("--version", help="show program's version number and exit",
                     action="version")
    parser.add_option_group(group)
    return parser

def add_restart_options(parser):
    parser.add_option("--restart-fraction", default=0.33, type="float", dest="restart_fraction",
                      help="Fraction of the cluster nodes rebooted at the same time (e.g. 0.33)")
    parser.add_option("--restart-timeout", default=600, type="int", dest="restart_timeout",
                      help="Seconds after which restart will timeout")
    return ['restart_fraction', 'restart_timeout']

def extract_options(keys, opts):
    values = map(lambda x: getattr(opts, x), keys)
    return dict(zip(keys, values))

def list_main(argv):
    usage = 'usage: %prog list [options] [context] [vhost]'
    parser = create_option_parser(usage)
    parser.add_option("--latest-only", action="store_true", dest="latest", 
                      default="False", help="Return the most recent version number for the webapps on the server")
    (opts, args) = parser.parse_args(argv)
    c = TomcatCluster(opts.host, opts.user, opts.passwd, opts.port)
    fmt = '{0:<25} {1:<15} {2:<10} {3:<12} {4:<5} {5:>8}'
    nmemb = len(c.members)
    print '\n', fmt.format('Context', 'Path', 'State', 'Version', 'Cohrn', 'Nodes')
    for k, a in c.webapp_status(latest=opts.latest, *args).iteritems():
        print fmt.format(
            k, a['path'], a['stateName'], a['webappVersion'], str(a['coherent']),
            '{0} / {1}'.format(len(a['presentOn']), nmemb) )

def deploy_main(argv):
    '''
    Deploy a webapp
    '''
    usage = 'usage: %prog deploy [options] WARFILE..'
    parser = create_option_parser(usage)
    parser.add_option("--kill-sessions", action="store_true", dest="kill_sessions",
                      help="Kill sessions before undeploying old versions")
    parser.add_option("--no-check-memory", action="store_false", dest="check_memory",
                      default=True, help="Do not check available memory on server(s)")
    parser.add_option("--required-memory", default=50, type="int", dest="required_memory",
                      help="Percentage of free memory required (e.g. 50)")
    parser.add_option("--no-auto-gc", action="store_false", dest="auto_gc", default=True,
                      help="Do not trigger GC on server(s) to reclaim memory")
    parser.add_option("--auto-restart", action="store_true", dest="auto_restart",
                      help="Automatically restart application server(s) on low memory")
    restart_options = add_restart_options(parser)
    deployer_options = restart_options + [
        'kill_sessions', 'check_memory', 'required_memory', 'auto_gc',
        'auto_restart' ]

    (opts, args) = parser.parse_args(argv)
    d = ClusterDeployer(**extract_options(conn_options + deployer_options, opts))
    d.deploy(parse_warfiles(args))

def undeploy_main(argv):
    '''
    Undeploy a webapp
    '''
    usage = 'usage: %prog undeploy [options] CONTEXT..'
    parser = create_option_parser(usage)
    (opts, args) = parser.parse_args(argv)
    d = ClusterDeployer(**extract_options(conn_options, opts))
    d.undeploy(args)

def restart_main(argv):
    '''
    Restart Tomcat on specified hosts
    For a cluster, the restart is performed in a rolling fashion
    '''
    usage = 'usage: %prog restart [options] [HOST..]'
    parser = create_option_parser(usage)
    restart_options = add_restart_options(parser)
    (opts, args) = parser.parse_args(argv)
    d = ClusterDeployer(**extract_options(conn_options + restart_options, opts))
    d.restart(args)

def rollback_main(argv):
    """
    Rollback web app to previously deployed build with checks to ensure each cluster member will have a build to run
      after the rollback. After the rollback is performed, there should be no users with active sessions on the build
      that was rolled back.
    """
    usage = 'usage: %prog rollback [options] CTX..'
    parser = create_option_parser(usage)
    (opts, args) = parser.parse_args(argv)
    d = ClusterDeployer(**extract_options(conn_options, opts))
    # TODO: Report results
    d.rollback(args)

def tool_main():
    from sys import argv
    setup_logging(logging.INFO, 'pytomcat')

    tools = { 'deploy'   : deploy_main,
              'undeploy' : undeploy_main,
              'restart'  : restart_main,
              'list'     : list_main,
              'rollback' : rollback_main }

    usage = 'usage: %prog COMMAND [options] [args]'
    epilog = 'Available commands: {0}'.format(' '.join(sorted(tools.keys())))
    parser = create_option_parser(usage, epilog)

    if len(argv) < 2 or argv[1] == 'help':
        parser.print_help()
        exit(2)

    tool = argv[1]
    if tool.startswith('-'):
        parser.parse_args(argv)
        parser.error('command name must be the first argument')

    if tool not in tools:
        parser.error("Unknown command '{0}'".format(tool))

    tools[tool](argv[2:])

    #setup_logging(logging.INFO, 'pytomcat.jmxproxy')
    #setup_logging(logging.DEBUG, 'pytomcat')
