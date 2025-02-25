"""
WebSocket双向OPUS音频传输系统
环境要求：Python 3.7+
依赖库：websocket-client, opuslib, pyaudio
"""
import websocket
import opuslib
import pyaudio
import threading
import time
import logging
import sys
import json
import queue
from collections import deque

# 全局配置
SAMPLE_RATE = 24000    # 24kHz采样率
CHANNELS = 1           # 单通道
FRAME_MS = 60          # 60ms帧长
CHUNK = SAMPLE_RATE * FRAME_MS // 1000  # 1440采样点
WS_URL = "ws://127.0.0.1:8000/v1"
MAX_QUEUE_SIZE = 30    # 音频队列最大长度

# 日志配置
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("AudioWSClient")

class OpusCodec:
    """OPUS编解码处理器"""
    def __init__(self):
        try:
            # 编码器配置
            self.encoder = opuslib.Encoder(
                SAMPLE_RATE,
                CHANNELS,
                opuslib.APPLICATION_VOIP
            )
            self.encoder.bitrate = 24000  # 24kbps
            self.encoder.signal = opuslib.SIGNAL_VOICE
            
            # 解码器配置
            self.decoder = opuslib.Decoder(SAMPLE_RATE, CHANNELS)
            logger.info("OPUS编解码器初始化成功")
        except opuslib.OpusError as e:
            logger.error(f"OPUS初始化失败: {e}")
            raise

    def encode(self, pcm: bytes) -> bytes:
        """PCM -> OPUS"""
        try:
            return self.encoder.encode(pcm, CHUNK)
        except opuslib.OpusError as e:
            logger.error(f"编码失败: {e}")
            return None

    def decode(self, opus: bytes) -> bytes:
        """OPUS -> PCM"""
        try:
            return self.decoder.decode(opus, CHUNK)
        except opuslib.OpusError as e:
            logger.error(f"解码失败: {e}")
            return None

class AudioIO:
    """音频输入输出管理"""
    def __init__(self):
        self.pa = pyaudio.PyAudio()
        self.input_queue = queue.Queue(maxsize=MAX_QUEUE_SIZE)
        self.output_buffer = deque(maxlen=MAX_QUEUE_SIZE)
        self._init_streams()

    def _init_streams(self):
        """初始化音频设备"""
        # 输入流（麦克风）
        self.input_stream = self.pa.open(
            format=pyaudio.paInt16,
            channels=CHANNELS,
            rate=SAMPLE_RATE,
            input=True,
            frames_per_buffer=CHUNK,
            stream_callback=self._input_callback
        )
        
        # 输出流（扬声器）
        self.output_stream = self.pa.open(
            format=pyaudio.paInt16,
            channels=CHANNELS,
            rate=SAMPLE_RATE,
            output=True,
            frames_per_buffer=CHUNK
        )
        logger.info("音频设备初始化完成")

    def _input_callback(self, in_data, frame_count, time_info, status):
        """麦克风数据回调"""
        self.input_queue.put(in_data)
        return (in_data, pyaudio.paContinue)

    def get_input_frame(self):
        """获取输入音频帧（非阻塞）"""
        try:
            return self.input_queue.get_nowait()
        except queue.Empty:
            return None

    def play_output(self, pcm_data):
        """播放输出音频"""
        if pcm_data:
            self.output_buffer.extend(pcm_data)
            try:
                self.output_stream.write(pcm_data)
            except OSError as e:
                logger.error(f"音频播放失败: {e}")

    def release(self):
        """释放音频资源"""
        self.input_stream.stop_stream()
        self.output_stream.stop_stream()
        self.input_stream.close()
        self.output_stream.close()
        self.pa.terminate()
        logger.info("音频资源已释放")

class AudioClient:
    """WebSocket音频客户端核心"""
    def __init__(self):
        self.ws = None
        self.codec = OpusCodec()
        self.audio = AudioIO()
        self.is_running = False
        self._init_websocket()
        self.sync_timer = 0
        self.ping_interval = 25  # 秒

    def _init_websocket(self):
        """初始化WebSocket连接"""
        self.ws = websocket.WebSocketApp(
            WS_URL,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
            header={
                "Protocol-Version": "2.0",
                "Audio-Config": f"{SAMPLE_RATE}/{CHANNELS}"
            }
        )

    def _on_open(self, ws):
        """连接建立处理"""
        logger.info(f"成功连接到服务器 {WS_URL}")
        self.is_running = True
        # 启动发送线程
        self.send_thread = threading.Thread(target=self._send_loop)
        self.send_thread.daemon = True
        self.send_thread.start()
        # 启动保活线程
        self.keepalive_thread = threading.Thread(target=self._keepalive)
        self.keepalive_thread.daemon = True
        self.keepalive_thread.start()

    def _send_loop(self):
        """音频发送主循环"""
        last_send = time.time()
        while self.is_running:
            try:
                # 精确时间控制
                elapsed = time.time() - last_send
                sleep_time = (FRAME_MS / 1000) - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)
                
                # 获取并编码音频
                if pcm_frame := self.audio.get_input_frame():
                    if opus_frame := self.codec.encode(pcm_frame):
                        self.ws.send(opus_frame, opcode=websocket.ABNF.OPCODE_BINARY)
                        last_send = time.time()
            except Exception as e:
                logger.error(f"发送异常: {e}")
                break

    def _keepalive(self):
        """连接保活机制"""
        while self.is_running:
            time.sleep(self.ping_interval)
            try:
                self.ws.send("PING", opcode=websocket.ABNF.OPCODE_PING)
            except Exception as e:
                logger.warning(f"心跳发送失败: {e}")

    def _on_message(self, ws, message):
        """消息处理"""
        if isinstance(message, bytes):
            self._handle_audio(message)
        else:
            self._handle_control(message)

    def _handle_audio(self, opus_frame):
        """处理音频数据"""
        if pcm_frame := self.codec.decode(opus_frame):
            self.audio.play_output(pcm_frame)

    def _handle_control(self, message):
        """处理控制消息"""
        try:
            data = json.loads(message)
            logger.info(f"控制消息: {data}")
            if data.get('type') == 'tts':
                if data['state'] == 'stop':
                    self.audio.output_buffer.clear()
        except json.JSONDecodeError:
            logger.warning(f"非法控制消息: {message}")

    def _on_error(self, ws, error):
        """错误处理"""
        logger.error(f"连接错误: {error}")
        self.is_running = False

    def _on_close(self, ws, code, reason):
        """关闭处理"""
        self.is_running = False
        logger.info(f"连接关闭 [{code}] {reason}")
        self._cleanup()

    def _cleanup(self):
        """资源清理"""
        self.audio.release()
        if self.ws:
            self.ws.close()
        logger.info("系统资源已释放")

    def run(self):
        """运行客户端"""
        retries = 0
        max_retries = 5
        while retries < max_retries:
            try:
                self.ws.run_forever(
                    ping_interval=30,
                    ping_timeout=15,
                    reconnect=3
                )
                break
            except Exception as e:
                logger.error(f"连接异常: {e}")
                retries += 1
                delay = min(2 ** retries, 30)
                logger.info(f"{delay}秒后尝试重连...")
                time.sleep(delay)
        else:
            logger.error("超过最大重试次数")

if __name__ == "__main__":
    client = AudioClient()
    try:
        client.run()
    except KeyboardInterrupt:
        client._cleanup()
        logger.info("用户中断操作")