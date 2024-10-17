### Build to generate tag
```shell
docker-compose build
```

output:
```shell
    Successfully built d8dd7bcb2375
    Successfully tagged nulink:latest
```
```shell
docker-compose ps or docker images
```

output:
```shell
    Name     Command    State    Ports
    -----------------------------------
    nulink   /bin/bash   Exit 0
```

```shell
docker login

docker tag nulink:latest nulink/nulink:latest

docker push nulink/nulink:latest
```

### how to run

```shell
docker pull nulink/nulink:latest

docker run  -p 127.0.0.1:19123:19123/tcp -v /path/host/Machine/directory:/code --rm -it nulink/nulink /bin/bash

# 注意： docker 的 porter启动必须在 /root/nulink 目录下 才能正常启动
docker run --restart on-failure -d \
                --name card-slot-porter \
                       -p 21106:21106 \
nulink/nulink:latest \
nulink porter run --network bsc_testnet --eth-provider https://bsc-testnet.blockpi.network/v1/rpc/8bb18ae7efff29171cfcfde05fed7f8a76d847a3 --teacher https://47.237.117.37:21107 --http-port 21106 --allow-origins * --console-logs
```