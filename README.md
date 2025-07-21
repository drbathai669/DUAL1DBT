
https://github.com/termux/termux-app/releases/download/v0.118.3/termux-app_v0.118.3+github-debug_x86_64.apk

pkg install python git -y

pkg install wget -y

wget https://raw.githubusercontent.com/drbathai669/DUAL1DBT/refs/heads/main/proxy.py

git clone https://github.com/drbathai669/DUAL1DBT.git

cd DUAL1DBT

python proxy.py

nano ~/startproxy.sh

#!/data/data/com.termux/files/usr/bin/bash 

cd ~/DUAL1DBT 

nohup python proxy.py > /dev/null 2>&1 &

chmod +x ~/startproxy.sh

echo 'bash ~/startproxy.sh' >> ~/.bashrc
