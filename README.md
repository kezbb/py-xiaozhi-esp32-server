# py-xiaozhi-esp32-server

## 项目简介
py-xiaozhi-esp32-server 是一个使用 Python 实现的小智语音客户端，旨在没有硬件条件下测试使用xiaozhi-esp32-server AI 小智的语音功能。

## 项目背景
- 根据xiaozhi-esp32-server开发的测试脚本：[xiaozhi-esp32-server](https://github.com/xinnan-tech/xiaozhi-esp32-server)

## 功能特点
- 语音交互
- websocket 通信
- 语音播放

## 环境要求
- Python 3.7+
- Windows

## 安装依赖

### Windows 环境
1. 克隆项目
```bash
git clone https://github.com/Huang-junsen/py-xiaozhi.git
cd py-xiaozhi
```

2. 安装 Python 依赖
```bash
pip install -r requirements.txt
```

3. 拷贝 opus.dll
- 将 `opus.dll` 拷贝到 `C:\Windows\System32` 目录

## 运行
```bash
python main.py
```

## 使用说明
- 启动脚本后，会自动连接
- 实时开始语音交互
- 实现播放音频

## 已知问题
- 偶尔读取不到音频，出现断开连接，需要重新连接
- 语音识别会识别到音频最后一句话语，需要优化

## 免责声明
本项目仅用于学习和研究目的，不得用于商业用途。