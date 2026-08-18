<#
    Пересборка окружения ComfyUI на Python 3.13
    ---------------------------------------------------------------
    Зачем: текущий .venv собран на Python 3.14, под который нет
    бинарников для tbg-etur (.pyd только 3.10-3.13) и nunchaku.
    ComfyUI официально рекомендует 3.13.

    Старый .venv НЕ удаляется, а переименовывается -> откат в 1 шаг.
    Запускать из обычного PowerShell (админ не нужен):

        cd D:\Project\ComfyUI
        powershell -ExecutionPolicy Bypass -File .\rebuild_py313.ps1
#>

$ErrorActionPreference = 'Stop'
$Root = 'D:\Project\ComfyUI'
Set-Location $Root

function Step($n, $t) { Write-Host "`n=== [$n] $t ===" -ForegroundColor Cyan }
function Warn($t)     { Write-Host "  ! $t" -ForegroundColor Yellow }
function Ok($t)       { Write-Host "  + $t" -ForegroundColor Green }

# ---------------------------------------------------------------- 0. проверки
Step 0 'Проверка окружения'

$free = (Get-PSDrive D).Free / 1GB
Write-Host ("  Свободно на D: {0:N1} GB" -f $free)
if ($free -lt 25) {
    Warn 'Меньше 25 GB. Старый venv + новый могут не поместиться.'
    Warn 'Освободи место или удали .venv вручную (тогда отката не будет).'
    if ((Read-Host '  Продолжить? (y/n)') -ne 'y') { exit 1 }
}

# Драйвер NVIDIA решает, какую сборку CUDA можно ставить.
# CUDA 13.0 требует драйвер r580+; иначе остаёмся на cu126 (как сейчас).
$cuda = 'cu126'
try {
    $drv = (& nvidia-smi --query-gpu=driver_version --format=csv,noheader) | Select-Object -First 1
    $drvMajor = [int]($drv -split '\.')[0]
    Write-Host "  Драйвер NVIDIA: $drv"
    if ($drvMajor -ge 580) {
        $cuda = 'cu130'
        Ok 'Драйвер поддерживает CUDA 13 -> ставим cu130 (включит оптимизированные ядра comfy-kitchen)'
    } else {
        Warn "Драйвер $drv < 580 -> остаёмся на cu126. Обнови драйвер и перезапусти, чтобы получить cu130."
    }
} catch {
    Warn 'nvidia-smi не найден, ставлю cu126 (безопасный вариант)'
}

# ---------------------------------------------------------------- 1. uv
Step 1 'uv (менеджер пакетов и версий Python)'
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host '  Ставлю uv...'
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}
Ok ("uv " + (& uv --version))

# ---------------------------------------------------------------- 2. Python 3.13
Step 2 'Python 3.13'
& uv python install 3.13
Ok 'Python 3.13 готов'

# ---------------------------------------------------------------- 3. новый venv
Step 3 'Новый .venv'
if (Test-Path '.venv') {
    $bak = '.venv-py314-backup'
    if (Test-Path $bak) { $bak = ".venv-backup-$(Get-Date -Format yyyyMMdd-HHmmss)" }
    Rename-Item '.venv' $bak
    Ok "старый venv сохранён как $bak"
}
& uv venv --python 3.13 --seed .venv
$py = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) { throw 'venv не создался - останавливаюсь, старый venv не тронут' }
Ok (& $py -c "import sys; print(sys.version)")

# констрейнты: не дать случайной зависимости перетереть torch другой сборкой
@'
torch==2.12.1
torchvision==0.27.1
torchaudio==2.11.0
'@ | Set-Content -Encoding ascii '.torch-constraints.txt'

# ---------------------------------------------------------------- 4. torch
Step 4 "PyTorch ($cuda)"
& $py -m pip install --upgrade pip --quiet
& $py -m pip install "torch==2.12.1+$cuda" "torchvision==0.27.1+$cuda" "torchaudio==2.11.0+$cuda" `
    --index-url "https://download.pytorch.org/whl/$cuda"
if ($LASTEXITCODE -ne 0) { throw "PyTorch ($cuda) не установился - дальше идти смысла нет" }
Ok (& $py -c "import torch; print('torch', torch.__version__, '| cuda', torch.version.cuda, '| gpu', torch.cuda.is_available())")

# ---------------------------------------------------------------- 5. ядро ComfyUI
Step 5 'Зависимости ComfyUI'
& uv pip install --python $py -c .torch-constraints.txt -r requirements.txt
& uv pip install --python $py -c .torch-constraints.txt -r manager_requirements.txt
Ok 'ядро установлено'

# ---------------------------------------------------------------- 6. кастомные ноды
Step 6 'Зависимости кастомных нод'
# pyopenjtalk и jieba_fast собираются только из исходников (нужен MSVC) -
# ставим отдельно в шаге 7, чтобы их падение не роняло весь цикл.
$skipDirs = @('ComfyUI-GPT_SoVITS')
$failed = @()
foreach ($dir in (Get-ChildItem 'custom_nodes' -Directory)) {
    $name = $dir.Name
    $req  = Join-Path $dir.FullName 'requirements.txt'
    if (-not (Test-Path $req)) { continue }
    if ($skipDirs -contains $name) { continue }
    Write-Host "  -> $name"
    $global:LASTEXITCODE = 0
    & uv pip install --python $py -c .torch-constraints.txt -r $req
    if ($LASTEXITCODE -ne 0) {
        Warn "$name : не установилось, разберём отдельно"
        $failed += $name
    }
}
if ($failed) { Warn ("Проблемные ноды: " + ($failed -join ', ')) } else { Ok 'все ноды ок' }

# ---------------------------------------------------------------- 7. то, чего не хватало
Step 7 'Пакеты, которых не было в старом окружении'
$extras = @(
    'gguf>=0.13.0',          # ComfyUI-GGUF - квантованные модели, критично для 8 GB
    'imageio-ffmpeg',        # VideoHelperSuite - запись видео
    'onnxruntime-gpu',       # DWPose на GPU вместо CPU
    'openexr',               # даёт модули OpenEXR и Imath (tbg-etur / NL_Nodes)
    'audiotsm',              # GPT_SoVITS
    'triton-windows==3.7.1.post27',  # tbg-etur
    'gtts', 'pydub'          # MyTTSNode
)
& uv pip install --python $py -c .torch-constraints.txt $extras

# ВАЖНО: onnxruntime-gpu ставит модуль в ТУ ЖЕ папку site-packages\onnxruntime,
# что и CPU-сборка. `pip uninstall onnxruntime` удаляет общие файлы и ломает
# GPU-сборку ("module 'onnxruntime' has no attribute 'InferenceSession'").
# Правильный порядок: снести обе и поставить только GPU заново.
$global:LASTEXITCODE = 0
& uv pip uninstall --python $py onnxruntime onnxruntime-gpu
$global:LASTEXITCODE = 0
& uv pip install --python $py -c .torch-constraints.txt --no-cache onnxruntime-gpu
$global:LASTEXITCODE = 0

# GPT_SoVITS без двух пакетов, требующих компилятор
Write-Host '  -> ComfyUI-GPT_SoVITS (без pyopenjtalk/jieba_fast)'
$sovits = Get-Content 'custom_nodes\ComfyUI-GPT_SoVITS\requirements.txt' |
          Where-Object { $_ -notmatch 'pyopenjtalk|jieba_fast' -and $_.Trim() -ne '' }
$sovits | Set-Content -Encoding ascii "$env:TEMP\sovits-req.txt"
$global:LASTEXITCODE = 0
& uv pip install --python $py -c .torch-constraints.txt -r "$env:TEMP\sovits-req.txt"
if ($LASTEXITCODE -ne 0) { Warn 'часть зависимостей GPT_SoVITS не встала - не критично' }
$global:LASTEXITCODE = 0

# ---------------------------------------------------------------- 8. проверка
Step 8 'Проверка'
& $py -c @"
import sys, importlib
print('Python  ', sys.version.split()[0])
import torch
print('torch   ', torch.__version__, '| CUDA', torch.version.cuda, '| GPU', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NOT AVAILABLE')
mods = ['gguf','librosa','kornia','imageio_ffmpeg','onnxruntime','triton','audiotsm','insightface','mediapipe','bitsandbytes','OpenEXR','Imath']
for m in mods:
    try:
        importlib.import_module(m); print(f'  ok      {m}')
    except Exception as e:
        print(f'  FAIL    {m}: {type(e).__name__}: {e}')
"@

Write-Host "`nГотово. Запускай ComfyUI как обычно и пришли новый comfyui.log." -ForegroundColor Green
Write-Host "Откат: удалить .venv и переименовать .venv-py314-backup обратно в .venv" -ForegroundColor DarkGray
