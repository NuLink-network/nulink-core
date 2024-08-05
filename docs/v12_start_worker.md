测试网 V12版本：

0.
首先需要让sam给你mint一个卡槽nft, 获取到此nft的 token id, 
并用此账户地址作为下面的初始化时 --signer参数的账户

设置环境变量
export NULINK_STAKING_PROVIDER_ETH_PASSWORD=qazwsxedc
export NULINK_KEYSTORE_PASSWORD=qazwsxedc
export NULINK_OPERATOR_ETH_PASSWORD=qazwsxedc

chmod -R 777 /root/nulink/worker-1

1. 需要先初始化: 
sudo docker run -it --rm \
-v /root/nulink/worker-1:/code \
-v /root/nulink/worker-1:/home/circleci/.local/share/nulink \
nulink/nulink:dev nulink stake init --signer keystore:///code/keystore/keystore-staker-5cd0a102013321f5bbf53dde4eb73e59d32539b2  --provider  https://data-seed-prebsc-1-s1.bnbchain.org:8545 --network bsc_dev_testnet  --force


2. 创建质押池: 
docker run -it --rm \
-e NULINK_STAKING_PROVIDER_ETH_PASSWORD \
-v /root/nulink/worker-1:/code \
-v /root/nulink/worker-1:/home/circleci/.local/share/nulink \
nulink/nulink:dev nulink stake create-staking-pool --gas-price 1000000000 --force --token-id 23

这里需要输入你的keystore的密码， 或者你设置环境变量NULINK_STAKING_PROVIDER_ETH_PASSWORD也可以
如果要指定质押初始化文件，则需要增加参数：
--config-file C:\\Users\\Administrator\\AppData\\Local\\NuLink\\nulink\\stakeholder-d9eca420ea4384ec4831cb4f785b1da08d5890af.json
这个参数路径 在第一步初始化时会输出

3. 绑定: 
docker run -it --rm \
-e NULINK_STAKING_PROVIDER_ETH_PASSWORD \
-v /root/nulink/worker-1:/code \
-v /root/nulink/worker-1:/home/circleci/.local/share/nulink \
nulink/nulink:dev nulink stake bond-worker --gas-price 1000000000 --force --worker-address 0xF3e30956ABacEF088a80C80A2F29E3e470190Aba --token-id 23

4. 解绑 docker run -it --rm \
-v /root/nulink/worker-1:/code \
-v /root/nulink/worker-1:/home/circleci/.local/share/nulink \
nulink/nulink:dev nulink stake unbond-worker  --gas-price 1000000000 --force --token-id 23


5.初始化worker
docker run -it --rm \
-p 9166:9166 \
-v /root/nulink/worker-1:/code \
-v /root/nulink/worker-1:/home/circleci/.local/share/nulink \
-e NULINK_KEYSTORE_PASSWORD \
nulink/nulink:dev nulink ursula init \
--signer keystore:///code/keystore/keystore-worker-f3e30956abacef088a80c80a2f29e3e470190aba \
--eth-provider https://data-seed-prebsc-2-s2.binance.org:8545 \
--network bsc_dev_testnet \
--payment-provider https://data-seed-prebsc-2-s2.binance.org:8545 \
--payment-network bsc_dev_testnet \
--operator-address 0xF3e30956ABacEF088a80C80A2F29E3e470190Aba \
--max-gas-price 10000000000 --rest-port 9166

6.启动worker (需要至少0.1TBNB和1000NLK,如果没有这些启动了，那么充值后需要重新启动该worker)
docker run --restart on-failure -d \
--name cross-chain-worker-1 \
-p 9166:9166 \
-v /root/nulink/worker-1:/code \
-v /root/nulink/worker-1:/home/circleci/.local/share/nulink \
-e NULINK_KEYSTORE_PASSWORD \
-e NULINK_OPERATOR_ETH_PASSWORD \
nulink/nulink:dev nulink ursula run --no-block-until-ready --file-logs --console-logs --rest-port 9166 

# 如果要指定配置文件，增加此参数： --config-file /code/ursula-026f993c.json


