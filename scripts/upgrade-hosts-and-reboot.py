#!/bin/python3

import subprocess
import getpass
import os
import time
import argparse

TERMINALID = int(time.time())

if not 'ANSIBLE_USER' in os.environ:
    print (f"no ANSIBLE_USER defined in environmental variables")
    exit()
if not 'ANSIBLE_PASSWORD' in os.environ:
    print (f"no ANSIBLE_PASSWORD defined in environmental variables")
    exit()

parser = argparse.ArgumentParser(prog='vep updater',
                                 description='This programe installs all updates on the selected vep group')

parser.add_argument('-t', '--nodetype', required=True, help='''available node types:
1) cluster primary nodes
2) cluster secondary nodes
3) non cluster nodes''')      # option that takes a value
parser.add_argument('-r', '--reboot', action='store_true', help='Reboot selected devices after upgrade finishes')
parser.add_argument('-l', '--list', action='store_true', help='Print node list')
parser.add_argument('--targets', default='none',
                    help='Limit target hosts (normal operation requires "all")')

args = parser.parse_args()

inventory_file = '/opt/ncubed/ansible/inventories/hosts.yaml'

if args.nodetype == '1':
    host_filter = 'grep "size: 2" | grep "member: 1"'
elif args.nodetype == '2':
    host_filter = 'grep "size: 2" | grep "member: 2"'
elif args.nodetype == '3':
    host_filter = 'grep "No such file or directory"'

r = subprocess.run(f'''
               ansible -T1 -o -i {inventory_file} -m shell -a "cat /opt/ncubed/config/local/system.yaml" {args.targets} 2> /dev/null | {host_filter} | cut -d " " -f1
               ''',
               shell=True, capture_output=True, text=True).stdout.strip("\n")

nodes = r.replace('\n',',')
if not nodes:
    print (f"No actionable nodes found in list ({args.targets})")
    exit()

if args.list:
    print (f"type {args.nodetype} nodes: {nodes}")
    exit()

print(f'Upgrading nodes: {nodes}')

r = subprocess.run(f'''
                    ansible -o -i {inventory_file} -m shell -a 'tmux new -s {TERMINALID} -d' {nodes}
                    ansible -o -i {inventory_file} -m shell -a 'tmux send-keys -t {TERMINALID} ACTIVE_NETNS=$(ip netns |grep $(ip -br addr | grep wg_ | grep -o -e "WAN\S*" -e "ROOT\S*"| head -1) | cut -d " " -f1) enter' {nodes}
                    
                    ansible -o -i {inventory_file} -m shell -a 'tmux send-keys -t {TERMINALID} "sudo ip netns exec \$ACTIVE_NETNS bash" enter' {nodes}
                    ansible -o -i {inventory_file} -m shell -a 'tmux send-keys -t {TERMINALID} "touch /opt/ncubed/apt_lock"' {nodes}
                    ansible -o -i {inventory_file} -m shell -a 'tmux send-keys -t {TERMINALID} " && DEBIAN_FRONTEND=noninteractive"' {nodes}
                    ansible -o -i {inventory_file} -m shell -a 'tmux send-keys -t {TERMINALID} " && apt -y update"' {nodes}
                    ansible -o -i {inventory_file} -m shell -a 'tmux send-keys -t {TERMINALID} " && apt -yq upgrade"' {nodes}
                    ansible -o -i {inventory_file} -m shell -a 'tmux send-keys -t {TERMINALID} " && rm /opt/ncubed/apt_lock"' {nodes}
                    ansible -o -i {inventory_file} -m shell -a 'tmux send-keys -t {TERMINALID} " && exit" enter' {nodes}
                    
                    ''',
                    shell=True, capture_output=True, text=True).stdout.strip("\n")

nodes_list = nodes.split(',')
while nodes_list:
    time.sleep(3)
    finished_nodes=[]
    for node in nodes_list:
        r = subprocess.run(f'''
                            ansible -o -i /opt/ncubed/ansible/inventories/hosts.yaml -m shell -a "tmux capture-pane -t {TERMINALID} -p" {node}
                            ''',
                            shell=True, capture_output=True, text=True).stdout.strip("\n")

        lines = r.split('\\n')
        if lines[-1][-3:] == ':~$':
            finished_nodes.append(nodes_list.index(node))
            lines.append('FINISHED')
            subprocess.run(f'''
                            ansible -o -i {inventory_file} -m shell -a "tmux send-keys -t {TERMINALID} 'exit' enter" {node}
                            ''',
                            shell=True)
        else:
            subprocess.run(f'''
                            ansible -o -i {inventory_file} -m shell -a "tmux send-keys -t {TERMINALID} enter" {node}
                            ''',
                            shell=True)

        print(f'{lines[0].split(" ")[0]} | {time.asctime()} | {lines[-1]}')
        finished_nodes.sort(reverse=True)
        for i in finished_nodes:
            nodes_list.pop(i)

if args.reboot:
    # reboot only if there is no apt_lock file in the /opt/ncubed folder
    subprocess.run(f'''
                ansible -o -i {inventory_file} -m shell -a "if [ ! -f /opt/ncubed/apt_lock ]; then sudo init 6; fi" {nodes}
                ''',
                shell=True)

pass
