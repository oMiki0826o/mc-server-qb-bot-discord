"""
core/minecraft/mc_pearl_config.py

Modification():

- 補上檔頭格式，數值與變數名稱都沒有變動。

Description():

- 珍珠砲計算機用的全域參數，/pearl 指令執行前會覆寫這幾個值，
  run() 再從這裡讀出來算。
"""

projectedPos = [0, 167.35, 0]
destination_x = 0
destination_z = 863
ground_height = 128
