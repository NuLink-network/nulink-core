all:
  children:
    nulink:
      children:
        ${deployer.network}:
          children:
            nodes:
              vars:
                network_name: "${deployer.network}"
                geth_options: "--${deployer.chain_name}"
                geth_dir: '/home/nulink/geth/.ethereum/${deployer.chain_name}/'
                geth_container_geth_datadir: "/root/.ethereum/${deployer.chain_name}"
                nulink_container_geth_datadir: "/root/.local/share/geth/.ethereum/${deployer.chain_name}"
                etherscan_domain: ${deployer.chain_name}.etherscan.io
                ansible_python_interpreter: /usr/bin/python3
                ansible_connection: ssh
                nulink_image: ${deployer.config['nulink_image']}
                blockchain_provider: ${deployer.config['blockchain_provider']}
                node_is_decentralized: ${deployer.nodes_are_decentralized}
                %if deployer.config.get('seed_node'):
                SEED_NODE_URI: ${deployer.config['seed_node']}
                teacher_options: ""
                %else:
                SEED_NODE_URI:
                teacher_options: ""
                %endif
                wipe_nulink_config: ${extra.get('wipe_nulink', False)}
                deployer_config_path: ${deployer.config_dir}
                restore_path: ${extra.get('restore_path')}
              hosts:
                %for node in nodes:
                ${node['publicaddress']}:
                  host_nickname: "${node['host_nickname']}"
                  %for attr in node['provider_deploy_attrs']:
                  ${attr['key']}: ${attr['value']}
                  %endfor
                  % if node.get('blockchain_provider'):
                  blockchain_provider: ${node['blockchain_provider']}
                  %endif
                  %if node.get('nulink_image'):
                  nulink_image: ${node['nulink_image']}
                  %endif
                  runtime_envvars:
                  %for key, val in node['runtime_envvars'].items():
                    ${key}: "${val}"
                  %endfor
                  nulink_ursula_run_options: ${deployer._format_runtime_options(node['runtime_cliargs'])}
                %endfor
