from mininet.topo import Topo
from mininet.net import Mininet
from mininet.link import TCLink
from mininet.log import setLogLevel
from mininet.cli import CLI
from mininet.clean import cleanup

from helper.util import print_error, print_warning, print_success
from helper.util import get_git_revision_hash, get_host_version, get_available_algorithms, check_tools
from helper.util import sleep_progress_bar

import os
import sys
import subprocess
import time
import argparse
import re


MAX_HOST_NUMBER = 256**2
GOODPUT_INTERVAL = 200


class DumbbellTopo(Topo):
    "Three switchs connected to n senders and receivers."

    def build(self, n=2):
        switch1 = self.addSwitch('s1')
        switch2 = self.addSwitch('s2')
        switch3 = self.addSwitch('s3')

        self.addLink(switch1, switch2)
        self.addLink(switch2, switch3)

        for h in range(n):
            host = self.addHost('h%s' % h, cpu=.5 / n)
            self.addLink(host, switch1)
            receiver = self.addHost('r%s' % h, cpu=1 / n)
            self.addLink(receiver, switch3)


def parseConfigFile(file):
    cc_algorithms = get_available_algorithms()

    unknown_alorithms = []
    number_of_hosts = 0
    output = []
    f = open(file)
    for line in f:
        line = line.replace('\n', '').strip()

        if len(line) > 1:
            if line[0] == '#':
                continue

        split = line.split(',')
        if split[0] == '':
            continue
        command = split[0].strip()

        if command == 'host':
            if len(split) != 5:
                print_warning('Too few arguments to add host in line\n{}'.format(line))
                continue
            algorithm = split[1].strip()
            rtt = split[2].strip()
            start = float(split[3].strip())
            stop = float(split[4].strip())
            if algorithm not in cc_algorithms:
                if algorithm not in unknown_alorithms:
                    unknown_alorithms.append(algorithm)
                continue

            if number_of_hosts >= MAX_HOST_NUMBER:
                print_warning('Max host number reached. Skipping further hosts.')
                continue

            number_of_hosts += 1
            output.append({
                'command': command,
                'algorithm': algorithm,
                'rtt': rtt,
                'start': start,
                'stop': stop})

        elif command == 'link':
            if len(split) != 4:
                print_warning('Too few arguments to change link in line\n{}'.format(line))
                continue
            change = split[1].strip()
            if change != 'bw' and change != 'rtt':
                print_warning('Unknown link option "{} in line\n{}'.format(change, line))
                continue
            value = split[2].strip()
            start = float(split[3].strip())
            output.append({
                'command': command,
                'change': change,
                'value': value,
                'start': start
            })
        else:
            print_warning('Skip unknown command "{}" in line\n{}'.format(command, line))
            continue

    if len(unknown_alorithms) > 0:
        print_warning('Skipping uninstalled congestion control algorithm:\n  ' + ' '.join(unknown_alorithms))
        print_warning('Available algorithms:\n  ' + cc_algorithms.strip())
        print_warning('Start Test anyway in 10s. (Press ^C to interrupt)')
        try:
            time.sleep(10)
        except KeyboardInterrupt:
            sys.exit(1)

    return output


def run_test(commands, directory, name, bandwidth, initial_rtt, buffer_size, buffer_limit, poll_interval):
    duration = 0
    start_time = 0
    number_of_hosts = 0

    output_directory = os.path.join(directory, '{}_{}'.format(time.strftime('%m%d_%H%M%S'), name))

    if not os.path.exists(output_directory):
        os.makedirs(output_directory)

    write_config = [
        'Test Name: {}'.format(name),
        'Date: {}'.format(time.strftime('%c')),
        'Kernel: {}'.format(get_host_version()),
        'Git Commit: {}'.format(get_git_revision_hash()),
        'Initial Bandwidth: {}'.format(bandwidth),
        'Burst Buffer: {}'.format(buffer_size),
        'Buffer Latency: {}'.format(buffer_limit),
        'Commands: '
    ]
    for cmd in commands:
        start_time += cmd['start']

        config_line = '{}, '.format(cmd['command'])
        if cmd['command'] == 'link':
            config_line += '{}, {}, {}'.format(cmd['change'], cmd['value'], cmd['start'])
        elif cmd['command'] == 'host':
            number_of_hosts += 1
            config_line += '{}, {}, {}, {}'.format(cmd['algorithm'], cmd['rtt'], cmd['start'], cmd['stop'])
            if start_time + cmd['stop'] > duration:
                duration = start_time + cmd['stop']
        write_config.append(config_line)

    with open(os.path.join('{}'.format(output_directory), 'parameters.txt'), 'w') as f:
        f.write('\n'.join(write_config))
        f.close()

    text_width = 60
    print('-' * text_width)
    print('Starting test: {}'.format(name))
    print('Total duration: {}s'.format(duration))

    try:
        topo = DumbbellTopo(number_of_hosts)
        net = Mininet(topo=topo, link=TCLink)
        net.start()
    except Exception as e:
        print_error('Could not start Mininet:')
        print_error(e)
        sys.exit(1)

    # start tcp dump
    try:
        FNULL = open(os.devnull, 'w')
        subprocess.Popen(['tcpdump', '-i', 's1-eth1', '-n', 'tcp', '-s', '88',
                          '-w', os.path.join(output_directory, 's1.pcap')], stderr=FNULL)
        subprocess.Popen(['tcpdump', '-i', 's3-eth1', '-n', 'tcp', '-s', '88',
                          '-w', os.path.join(output_directory, 's3.pcap')], stderr=FNULL)
    except Exception as e:
        print_error('Error on starting tcpdump\n{}'.format(e))
        sys.exit(1)

    # start tcpprobe
    os.system('modprobe -r tcp_probe')
    os.system('modprobe tcp_probe full=1 port=5000')
    os.system('chmod 444 /proc/net/tcpprobe')
    os.system('timeout {} cat /proc/net/tcpprobe > {} &'.format(duration, os.path.join(output_directory, 'tcpprobe.xls')))


    time.sleep(1)

    host_counter = 0
    for cmd in commands:
        if cmd['command'] != 'host':
            continue
        send = net.get('h{}'.format(host_counter))
        send.setIP('10.1.{}.{}/8'.format(host_counter / 256, host_counter % 256))
        recv = net.get('r{}'.format(host_counter))
        recv.setIP('10.2.{}.{}/8'.format(host_counter / 256, host_counter % 256))
        host_counter += 1

        # setup FQ, algorithm, netem, nc host
        if cmd['algorithm'] == 'bbr' or cmd['algorithm'] == 'nv' or cmd['algorithm'] == 'mybbr':
            send.cmd('tc qdisc add dev {}-eth0 root fq pacing'.format(send))
        else:
            send.cmd('tc qdisc add dev {}-eth0 root pfifo_fast')
        send.cmd('ip route change 10.0.0.0/8 dev {}-eth0 congctl {}'.format(send, cmd['algorithm']))
        send.cmd('ethtool -K {}-eth0 tso off'.format(send))
        recv.cmd('tc qdisc add dev {}-eth0 root netem delay {}'.format(recv, cmd['rtt']))
        recv.cmd('tcpdump -i {}-eth0 -n tcp -s 88 > {} &'.format(recv, os.path.join(output_directory,'{}.txt'.format(recv))))
        #recv.cmd('timeout {} nc -klp 9000 > /dev/null &'.format(duration))
        #recv.cmd('iperf -s -p 5000 &')
        #recv.cmd('./goodput.sh .5 {} &'.format(output_directory,'goodput_{}.txt'.format(recv.IP())));
        #recv.cmd('./goodput.sh 100 {} &'.format(os.path.join(output_directory,'goodput_{}.txt'.format(recv.IP()))))
        recv.cmd('./server 5000 {} {} &'.format(os.path.join(output_directory,'{}.goodput'.format(recv)),GOODPUT_INTERVAL))

        #time.sleep(1)
        #recv.cmd('sudo python TCPserver.py > ./goodputResult.txt &')
        # pull BBR values
        send.cmd('./ss_script.sh {} >> {}.bbr &'.format(poll_interval, os.path.join(output_directory, send.IP())))

    s2, s3 = net.get('s2', 's3')
    s2.cmd('tc qdisc add dev s2-eth2 root tbf rate {} buffer {} limit {}'.format(bandwidth, buffer_size, buffer_limit))
    netem_running = False
    if initial_rtt != '0ms':
        netem_running = True
        s2.cmd('tc qdisc add dev s2-eth1 root netem delay {}'.format(initial_rtt))
    s2.cmd('./buffer_script.sh {0} {1} >> {2}.buffer &'.format(poll_interval, 's2-eth2',
                                                               os.path.join(output_directory, 's2-eth2-tbf')))

    complete = duration
    current_time = 0

    host_counter = 0

    try:
        for cmd in commands:
            start = cmd['start']
            current_time = sleep_progress_bar(start, current_time=current_time, complete=complete)

            if cmd['command'] == 'link':
                s2 = net.get('s2')
                if cmd['change'] == 'bw':
                    s2.cmd('tc qdisc change dev s2-eth2 root tbf rate {} buffer {} limit {}'.format(cmd['value'], buffer_size, buffer_limit))
                    print("Bottleneck : " + str(cmd['value']))
                    log_String = '  Change bandwidth to {}.'.format(cmd['value'])
                elif cmd['change'] == 'rtt':
                    if netem_running:
                        s2.cmd('tc qdisc change dev s2-eth1 root netem delay {}'.format(cmd['value']))
                    else:
                        netem_running = True
                        s2.cmd('tc qdisc add dev s2-eth1 root netem delay {}'.format(cmd['value']))
                    log_String = '  Change rtt to {}.'.format(cmd['value'])

            elif cmd['command'] == 'host':
                send = net.get('h{}'.format(host_counter))
                recv = net.get('r{}'.format(host_counter))
                timeout = cmd['stop']
                log_String = '  h{}: {} {}, {} -> {}'.format(host_counter, cmd['algorithm'], cmd['rtt'], send.IP(), recv.IP())
                #send.cmd('timeout {} nc {} 9000 < /dev/urandom > /dev/null &'.format(timeout, recv.IP()))
                send.cmd('iperf -c {} -p 5000 -t {} -i 0.5 &'.format(recv.IP(),cmd['stop'], os.path.join(output_directory,'sender_iperf.txt'.format(send.IP()))))
                host_counter += 1
            print(log_String + ' ' * (text_width - len(log_String)))

        current_time = sleep_progress_bar((complete - current_time) % 1, current_time=current_time, complete=complete)
        current_time = sleep_progress_bar(complete - current_time, current_time=current_time, complete=complete)
    except (KeyboardInterrupt, Exception) as e:
        if isinstance(e, KeyboardInterrupt):
            print_warning('\nReceived keyboard interrupt. Stop Mininet.')
        else:
            print_error(e)
    finally:
        time.sleep(3)
        net.stop()
        cleanup()

    print('-' * text_width)


def verify_arguments(args, commands):
    verified = True

    verified &= verify('rate', args.bandwidth)
    verified &= verify('time', args.rtt)
    verified &= verify('size', args.buffer_size)
    verified &= verify('size', args.limit)

    for c in commands:
        if c['command'] == 'link':
            if c['change'] == 'bw':
                verified &= verify('rate', c['value'])
            elif c['change'] == 'rtt':
                verified &= verify('time', c['value'])
        elif c['command'] == 'host':
            verified &= verify('time', c['rtt'])

    return verified


def verify(type, value):
    if type == 'rate':
        allowed = ['bit', 'kbit', 'mbit', 'bps', 'kbps', 'mbps']
    elif type == 'time':
        allowed = ['s', 'ms', 'us']
    elif type == 'size':
        allowed = ['b', 'kbit', 'mbit', 'kb', 'k', 'mb', 'm']
    else:
        allowed = []  # Unknown type

    si = re.sub('^([0-9]+\.)?[0-9]+', '', value).lower()

    if si not in allowed:
        print_error('Malformed {} unit: {} not in {}'.format(type, value, list(allowed)))
        return False
    return True


if __name__ == '__main__':
    if check_tools() > 0:
        exit(1)

    parser = argparse.ArgumentParser()
    parser.add_argument('config', metavar='CONFIG',
                        help='Path to the config file.')
    parser.add_argument('-b', dest='bandwidth',
                        default='10Mbit', help='Initial bandwidth of the bottleneck link. (default: 10mbit)')
    parser.add_argument('-r', dest='rtt',
                        default='0ms', help='Initial rtt for all flows. (default 0ms)')
    parser.add_argument('-d', dest='directory',
                        default='test/', help='Path to the output directory. (default: test/)')
    parser.add_argument('-s', dest='buffer_size',
                        default='1600b', help='Maximum size of bottleneck buffer. (default : 62500b)')
    parser.add_argument('-l', dest='limit',
                        default='62500b', help='Maximum latency at the bottleneck buffer. (default: 100ms)')
    parser.add_argument('-n', dest='name',
                        default='TCP', help='Name of the output directory. (default: TCP)')
    parser.add_argument('--poll-interval', dest='poll_interval', type=float,
                        default=0.04, help='Interval to poll TCP values and buffer backlog in seconds. (default: 0.04)')

    args = parser.parse_args()

    if not os.path.isfile(args.config):
        print_error('Config file missing: {}'.format(args.config))
        sys.exit(128)

    commands = parseConfigFile(args.config)
    if len(commands) == 0:
        print_error('No valid commands found in config file.')
        sys.exit(128)

    if not verify_arguments(args, commands):
        print_error('Please fix malformed parameters.')
        sys.exit(128)

    print(args.bandwidth)

    # setLogLevel('info')
    run_test(bandwidth=args.bandwidth,
             initial_rtt=args.rtt,
             commands=commands,
             buffer_size=args.buffer_size,
             buffer_limit=args.limit,
             name=args.name,
             directory=args.directory,
             poll_interval=args.poll_interval)
