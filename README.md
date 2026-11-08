# Acoustic Link Lab

声波文本通信实验系统：使用电脑扬声器发送文本，通过另一台设备的麦克风录音，再自动同步、解调、纠错和重组。

包含基础 **BFSK** 与自主 **4FSK＋Hamming(15,11)＋块交织＋CRC-16** 两种方案，使用 React 界面和 Python 信号处理程序。支持录音后离线解码。

## 功能

- 输入40～80个可打印ASCII字符，每包10字符，末包按实际长度发送。
- 自动生成一段连续发送音频，自动检测接收录音中的数据包。
- 4FSK对包头和数据分别纠错，并通过CRC-16检查完整包。
- 波形、频谱、音频播放、手机录音导入、逐包结果和文本对比。
- 丢包率、BER、有效吞吐和完整文本恢复率，保留分子、分母与样本量。
- 安静速率、宽带噪声和带内单音干扰的配对测试与曲线汇总。

## 环境与启动

Python 3.10及以上。已附带构建好的前端，直接运行时只需安装Python依赖。以下命令在仓库根目录执行。

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe Code/initialize.py
.\.venv\Scripts\python.exe Code/web_app.py --open
```

安装依赖后，也可双击 `启动界面.cmd`。初次运行生成14段正式测试的发送音频；再次运行沿用现有实验。尚未录音的旧计划可运行 `python Code/initialize.py --compact`，旧发送文件先备份到work。

macOS / Linux：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python Code/initialize.py
.venv/bin/python Code/web_app.py --open
```

页面地址为 `http://127.0.0.1:8765/`。服务只监听本机，按 `Ctrl+C` 停止。需要另一个端口时使用 `--port 8767`。Windows启动流程已验证，macOS/Linux可使用上述Python入口。

## 录音操作

1. 从左侧清单的01、02开始，固定电脑和手机的位置，记录距离与系统音量。这两段同时用于设备检查和正式测试。
2. 手机录音机提前2秒开始，电脑通过扬声器完整播放当前实验的tx.wav。
3. 播放结束后继续录制2秒，保存手机原始录音。
4. 按页面编号命名录音，如01_BFSK、02_4FSK。在对应实验中选择文件，填写实际条件，点击“导入并解码”。

预设58字符文本、10ms符号时长下，BFSK播放10.48秒，新4FSK播放8.34秒。界面默认记录本实验的魔霸新锐2023和vivo X200s；使用其他设备时，可通过命令行导入并在conditions.json中填写实际设备。

首尾静音和全部数据包保存在同一轮录音中。程序保存原文件，并将完整首声道转换为rx.wav。默认每个目录保存一次采集，重复试验创建新目录。

## 精简录音计划

首轮14段，按页面01～14依次录制。每组BFSK和4FSK使用同一段文本和同一条件。

| 编号 | 条件 | 文本 | BFSK / 4FSK播放时长 |
| --- | --- | --- | --- |
| 01、02 | 安静，10 ms | A | 10.48 / 8.34 s |
| 03、04 | 安静，20 ms | B | 18.64 / 14.38 s |
| 05、06 | 安静，5 ms | C | 6.32 / 5.21 s |
| 07、08 | 噪声0.5，10 ms | B | 10.32 / 8.19 s |
| 09、10 | 噪声1.0，10 ms | C | 10.64 / 8.42 s |
| 11、12 | 带内干扰0.5，10 ms | B | 10.32 / 8.19 s |
| 13、14 | 带内干扰1.0，10 ms | C | 10.64 / 8.42 s |

0.5、1.0表示播放端干扰RMS与信号名义RMS的比值，干扰已混入对应音频。带内干扰为2 kHz单音。
01、02同时作为噪声、带内干扰曲线的零点；每条曲线包含A、B、C三段不同文本。14份独立录音只计14轮，共用基线保持相同文件来源。每点每方案初始样本量为1，统计表同时保留分子、分母和轮数。

先导入01、02检查实际设备，再完成其余12段。整轮固定设备、距离和系统音量。若需要调整设备位置或音量，另建一套同条件清单并保留已录数据。

曲线达到成功到明显下降的范围后，在转折不清楚的位置补一个中间点；最高干扰仍全成功时继续增强干扰。速率测试先覆盖允许范围的20、10、5 ms，根据吞吐变化再补8或15 ms。同一条件出现异常波动时用另一段文本复测。网页“结果汇总 → 添加补测点”每次新增2段，也可用命令行的`--add-point`和`--text-index 1|2|3`。最终数量由真实曲线决定。

界面保留“录音实验”和“结果汇总”两页。文本输入与方案设置在“自定义发送”中，波形/频谱、逐包同步校验、原文/恢复文本和四项指标均可查看。

## 目录与数据

```text
Code/                 调制、纠错、接收、统计和实验管理
  frontend/src/       React源码
  frontend/dist/      可直接运行的网页资源
tests/                35项Python测试及前端曲线分组检查
requirements.txt      Python依赖
启动界面.cmd           Windows启动入口
```

运行后生成的目录：

| 目录 | 内容 |
| --- | --- |
| Data/formal | 正式测试清单及逐轮音频、文本、参数 |
| Data/custom | 网页创建的自定义实验 |
| Results/formal | 逐轮指标、汇总表及实测曲线 |
| work | 自动测试的临时数据 |

这些本机实验目录已配置Git忽略规则。发送音频可以由代码和测试清单重新生成；手机原始录音由实验者采集并单独备份。课件、课程报告和视频保存在课程工作目录中。

每轮主要文件：`tx.wav`发送信号、`send.txt`原文、`original.*`手机原件、`rx.wav`完整接收音频、`rec.txt`恢复文本、`protocol.json`公开协议配置、`conditions.json`实际条件、`decoded.json`逐包判决、`metrics.json`统计结果。

## 协议和指标

统一48kHz；BFSK载波为2/3kHz，4FSK为1.5/2/2.5/3kHz；符号时长5～20ms，包间隔0.2秒，首尾各0.5秒静音。

逻辑包包含前导码 `D3 91 AC 6B`、总包数、序号、长度、Payload和校验。BFSK使用异或校验，自主方案使用CRC-16/CCITT-FALSE。4FSK将包头与Payload加CRC分别进行Hamming(15,11)编码，按列交织后映射为四频符号。码字位置1/2/4/8为偶校验位，其余位置依序填信息位，尾部补零。接收端根据已知前导码自动定位，先纠正包头，再按长度读取数据块，最后校验CRC。

接收器输入为完整录音和公开协议配置；原文在解码后用于评测。旧4FSK配置的`coding`为`none`，新实验默认`hamming15_11`。

- 丢包率：未成功接收的逻辑包数／应发逻辑包数。成功要求序号、校验和Payload均正确，重复包去重。
- BER：最终Payload错误位／实际比较位；4FSK在纠错后统计，包含可对齐的校验失败包。另外保存纠错前Payload统计。
- 有效吞吐：正确交付的去重Payload位数／完整tx.wav时长，包含协议开销、间隔和首尾静音。
- 完整文本恢复率：完整恢复原文的轮数／总轮数。

以58字符、10ms为例，全部正确接收时有效吞吐为BFSK 44.27bit/s、新4FSK 55.64bit/s。实际性能对比使用相同设备、位置、音量、文本和干扰条件下的手机录音。

## 命令行与开发

下面的`python`指安装了依赖的Python解释器；Windows可替换为`.\.venv\Scripts\python.exe`。

```bash
# 独立接收：仅需录音和公开配置
python Code/receiver.py --input Data/formal/quiet_0_T10_R1_4FSK/rx.wav --protocol Data/formal/quiet_0_T10_R1_4FSK/protocol.json --output Results/standalone.json

# 按实验目录重新解码、评测
python Code/workflow.py decode --folder Data/formal/quiet_0_T10_R1_4FSK
python Code/workflow.py evaluate --folder Data/formal/quiet_0_T10_R1_4FSK

# 导入录音，conditions.json记录实际条件
python Code/workflow.py import --folder Data/formal/quiet_0_T10_R1_4FSK --source phone.m4a --conditions conditions.json

# 汇总正式实验；在性能转折处增加一对录音
python Code/summary.py
python Code/batch.py --output Data/formal --add-point noise 0.75 10
```

conditions.json示例（按实际情况填写）：

```json
{
  "playback_device": "电脑扬声器",
  "recording_device": "手机录音机",
  "distance_m": 0.7,
  "system_volume": 50,
  "environment": "安静宿舍"
}
```

前端修改需要Node.js，已验证版本22.21.0：

```bash
npm --prefix Code/frontend ci
npm --prefix Code/frontend run build
```

开发时可运行`npm --prefix Code/frontend run dev`，同时运行Python服务。前端接口转发到8765端口。

## 验证与当前进度

```bash
python Code/initialize.py
python -m unittest discover -s tests -p "test_*.py" -v
node tests/test_chart.mjs
```

软件验证包含35项测试、100组收发参数组合，覆盖纠错、交织、随机起点、缺包、重复包、44.1kHz录音、时钟偏差和HTTP导入流程。测试使用软件生成的波形。

当前软件实现与发送文件准备已完成。真实录音、实测曲线、课程报告的实验结论和演示视频随采集进度补充。`Code/audit.py`用于课程工作目录中的最终交付检查，检查范围包含本仓库以外单独保存的报告与视频。
