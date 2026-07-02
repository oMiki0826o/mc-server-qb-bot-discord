"""
core/minecraft/mc_pearl_calculator.py

Modification():

- 修正 import 路徑：from minecraft import mc_pearl_config
  改成 from core.minecraft import mc_pearl_config，
  對齊這個專案實際的資料夾結構（原本的寫法在這裡 import 不到）。
- 內部註解統一改成這個專案的區塊註解格式，簡體字改繁體字。
  運算邏輯、公式、數值一律沒有更動。

Description():

- 珍珠砲（TNT 砲）落點計算核心：輸入珍珠位置與目的地座標，
  逐 tick 搜尋，輸出誤差最小的前 10 組 tick 數與對應的紅石訊號碼。
"""

import struct

from core.minecraft import mc_pearl_config


# ── float32 精度轉換 ──────────────────────

def float32_to_float64(val):
    packed = struct.pack('!f', val)
    return struct.unpack('!f', packed)[0]


# ── 數值轉紅石訊號位元字串 ──────────────────────

def num_to_bits(num):
    values = [80, 40, 20, 10, 4, 3, 2, 1]
    bits = []

    for v in values:
        if num >= v:
            bits.append('1')
            num -= v
        else:
            bits.append('0')

    b = ''.join(bits)
    return f"{b[:4]} {b[4:]}"


def run():

    # ── 讀取設定值 ──────────────────────
    ground_height = mc_pearl_config.ground_height
    projectedPos = mc_pearl_config.projectedPos
    destination_x = mc_pearl_config.destination_x
    destination_z = mc_pearl_config.destination_z

    # ── 物理常量（保持原始精度） ──────────────────────
    g = 0.03
    f = float32_to_float64(0.99)  # 精確模擬 numpy 的精度轉換

    one_tnt_motion_xz = 0.6026793588895138
    one_tnt_motion_y = 0.004435058914919521
    projectedMotion = [0.0, -0.340740225070415, 0.0]

    directions_mapping = {
        'N': '00',
        'W': '01',
        'E': '10',
        'S': '11',
    }

    deltax = destination_x - projectedPos[0]
    deltaz = destination_z - projectedPos[2]

    # ── 判斷主方向 ──────────────────────
    if abs(deltax) > abs(deltaz):
        direction = 'E' if deltax > 0 else 'W'
    else:
        direction = 'S' if deltaz > 0 else 'N'

    fly_tick_num = 1
    results = []

    while True:
        # ── 計算運動係數 ──────────────────────
        kp = 2 * one_tnt_motion_xz * ((f - f ** (fly_tick_num + 1)) / (1 - f))

        # ── 計算 m 與 n 值 ──────────────────────
        if direction in ('N', 'S'):
            m = round((deltax + deltaz) / kp)
            n = round((deltaz - deltax) / kp)

            if direction == 'N':
                m, n = n, m

            motion_x = (abs(m) - abs(n)) * one_tnt_motion_xz
            motion_y = abs(m + n) * one_tnt_motion_y + projectedMotion[1]
            motion_z = (m + n) * one_tnt_motion_xz

        else:
            m = round((deltax + deltaz) / kp)
            n = round((deltax - deltaz) / kp)

            if direction == 'W':
                m, n = n, m

            motion_x = (m + n) * one_tnt_motion_xz
            motion_y = abs(m + n) * one_tnt_motion_y + projectedMotion[1]
            motion_z = (abs(m) - abs(n)) * one_tnt_motion_xz

        # ── 邊界檢查 ──────────────────────
        if abs(m) > 160 or abs(n) > 160:
            fly_tick_num += 1
            continue

        # ── 初始化位置與動量 ──────────────────────
        pos_x, pos_y, pos_z = projectedPos
        cmx, cmy, cmz = motion_x, motion_y, motion_z

        # ── 模擬珍珠飛行 ──────────────────────
        for _ in range(fly_tick_num):
            cmx *= f
            cmy = (cmy - g) * f
            cmz *= f

            pos_x += cmx
            pos_y += cmy
            pos_z += cmz

        # ── 碰撞檢測 ──────────────────────
        if pos_y <= ground_height:
            break

        # ── 計算誤差 ──────────────────────
        error = (pos_x - destination_x) ** 2 + (pos_z - destination_z) ** 2

        text = (
            f"tick cost:{fly_tick_num} code:"
            + num_to_bits(round(abs(n)))[::-1] + " "
            + directions_mapping[direction] + " "
            + num_to_bits(round(abs(m))) +
            f"  tick:{fly_tick_num + 84}   "
            f"Pos:[{pos_x:.2f}, {pos_y:.2f}, {pos_z:.2f}]  "
            f"error:{error ** 0.5:.2f}")

        results.append((error, text))

        fly_tick_num += 1

    # ── 依誤差排序，取前 10 名 ──────────────────────
    results.sort(key=lambda x: x[0])

    output = []
    for i, (_, text) in enumerate(results[:10], 1):
        output.append(f"[{i}] {text}")

    return "\n".join(output)
