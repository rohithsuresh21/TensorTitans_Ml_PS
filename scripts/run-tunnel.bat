@echo off
set EXE=E:\MEGA\Hackathon\TensorTitans_Ml_PS\cloudflared.exe
"%EXE%" tunnel --url http://localhost:8000 --no-autoupdate 1> E:\MEGA\Hackathon\TensorTitans_Ml_PS\tunnel.out 2> E:\MEGA\Hackathon\TensorTitans_Ml_PS\tunnel.err
