import math
import zlib
import struct
import os

def create_png(width, height, rgba_data):
    """Create a raw PNG from RGBA bytes using standard zlib."""
    header = b'\x89PNG\r\n\x1a\n'
    
    # IHDR chunk
    ihdr_data = struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)
    ihdr_crc = zlib.crc32(b'IHDR' + ihdr_data)
    ihdr = struct.pack('>I', len(ihdr_data)) + b'IHDR' + ihdr_data + struct.pack('>I', ihdr_crc)
    
    # IDAT chunk
    raw_rows = []
    stride = width * 4
    for y in range(height):
        raw_rows.append(b'\x00' + rgba_data[y * stride : (y + 1) * stride])
    compressed = zlib.compress(b''.join(raw_rows), 9)
    idat_crc = zlib.crc32(b'IDAT' + compressed)
    idat = struct.pack('>I', len(compressed)) + b'IDAT' + compressed + struct.pack('>I', idat_crc)
    
    # IEND chunk
    iend_crc = zlib.crc32(b'IEND')
    iend = struct.pack('>I', 0) + b'IEND' + struct.pack('>I', iend_crc)
    
    return header + ihdr + idat + iend

def create_ico(png_images):
    """
    Build a multi-resolution ICO file from a list of (width, height, png_bytes).
    Modern Windows fully supports PNGs embedded in .ico.
    """
    num = len(png_images)
    header = struct.pack('<HHH', 0, 1, num)
    
    dir_entries = []
    offset = 6 + (num * 16)
    
    for w, h, png_bytes in png_images:
        w_byte = 0 if w >= 256 else w
        h_byte = 0 if h >= 256 else h
        size = len(png_bytes)
        entry = struct.pack('<BBBBHHII', w_byte, h_byte, 0, 0, 1, 32, size, offset)
        dir_entries.append(entry)
        offset += size
        
    return header + b''.join(dir_entries) + b''.join(p[2] for p in png_images)

def render_logo(size=256):
    # Render with 2x supersampling for ultra smooth anti-aliased edges
    scale = 2
    W = size * scale
    H = size * scale
    cx = W / 2.0
    cy = H / 2.0
    
    buf = bytearray(W * H * 4)
    
    def blend(x, y, r, g, b, a):
        if x < 0 or x >= W or y < 0 or y >= H or a <= 0:
            return
        idx = (y * W + x) * 4
        sa = a / 255.0
        da = buf[idx + 3] / 255.0
        out_a = sa + da * (1.0 - sa)
        if out_a > 0:
            buf[idx + 0] = int((r * sa + buf[idx + 0] * da * (1.0 - sa)) / out_a)
            buf[idx + 1] = int((g * sa + buf[idx + 1] * da * (1.0 - sa)) / out_a)
            buf[idx + 2] = int((b * sa + buf[idx + 2] * da * (1.0 - sa)) / out_a)
            buf[idx + 3] = int(min(255, out_a * 255))
            
    # Draw dark rounded squircle badge with soft dark metallic space gradient
    R = W * 0.45
    for y in range(H):
        for x in range(W):
            dx = (x - cx)
            dy = (y - cy)
            # Superellipse squircle formula: (x/r)^4 + (y/r)^4 <= 1
            nx = abs(dx) / R
            ny = abs(dy) / R
            d_squircle = (nx**3.6 + ny**3.6)**(1.0 / 3.6)
            
            if d_squircle <= 1.05:
                # Anti-aliasing edge factor
                edge_t = max(0.0, min(1.0, (1.05 - d_squircle) / 0.05))
                
                # Outer gold rim glow
                if d_squircle >= 0.88:
                    rim_t = (d_squircle - 0.88) / (1.05 - 0.88)
                    # Glowing Plex Gold border
                    gr = int(229 + (255 - 229) * (1.0 - rim_t))
                    gg = int(160 + (215 - 160) * (1.0 - rim_t))
                    gb = int(13 + (50 - 13) * (1.0 - rim_t))
                    alpha = int(255 * edge_t)
                    blend(x, y, gr, gg, gb, alpha)
                else:
                    # Deep cosmic background with subtle gradient
                    t_grad = (y / float(H))
                    # Top: deep navy-slate #1A1E24, Bottom: dark space obsidian #0C0E12
                    br = int(26 * (1.0 - t_grad) + 12 * t_grad)
                    bg = int(30 * (1.0 - t_grad) + 14 * t_grad)
                    bb = int(36 * (1.0 - t_grad) + 18 * t_grad)
                    blend(x, y, br, bg, bb, int(255 * edge_t))

    # Draw planetary / orbit space ring (slanted ellipse)
    ring_cx = cx
    ring_cy = cy + W * 0.02
    for angle_deg in range(0, 360):
        rad = math.radians(angle_deg)
        # 35 degree tilt
        tilt = math.radians(-25)
        rx = math.cos(rad) * (W * 0.46)
        ry = math.sin(rad) * (W * 0.16)
        
        rot_x = ring_cx + rx * math.cos(tilt) - ry * math.sin(tilt)
        rot_y = ring_cy + rx * math.sin(tilt) + ry * math.cos(tilt)
        
        # Color gradient around the ring: cyan glow to warm gold
        ring_t = (angle_deg % 180) / 180.0
        rr = int(255 * (1 - ring_t) + 79 * ring_t)
        rg = int(192 * (1 - ring_t) + 195 * ring_t)
        rb = int(30 * (1 - ring_t) + 247 * ring_t)
        
        # Draw particle brush
        for ox in range(-3, 4):
            for oy in range(-3, 4):
                dist = math.hypot(ox, oy)
                if dist <= 3.2:
                    ring_alpha = max(0.0, 1.0 - (dist / 3.2)) * 0.45
                    blend(int(rot_x + ox), int(rot_y + oy), rr, rg, rb, int(255 * ring_alpha))

    # Function to test if point (px, py) is inside the iconic Plex Chevron:
    # Original SVG: M9 7L24 20L9 33H16L31 20L16 7H9Z in 40x40 box
    # Scale from 40x40 to our canvas
    svg_scale = (W * 0.58) / 40.0
    svg_off_x = cx - (20.0 * svg_scale)
    svg_off_y = cy - (20.0 * svg_scale)
    
    # Polygon 1: Left chevron / outer chevron
    poly = [
        (9 * svg_scale + svg_off_x, 7 * svg_scale + svg_off_y),
        (24 * svg_scale + svg_off_x, 20 * svg_scale + svg_off_y),
        (9 * svg_scale + svg_off_x, 33 * svg_scale + svg_off_y),
        (16 * svg_scale + svg_off_x, 33 * svg_scale + svg_off_y),
        (31 * svg_scale + svg_off_x, 20 * svg_scale + svg_off_y),
        (16 * svg_scale + svg_off_x, 7 * svg_scale + svg_off_y),
    ]
    
    def point_in_poly(px, py, polygon):
        inside = False
        n = len(polygon)
        p1x, p1y = polygon[0]
        for i in range(1, n + 1):
            p2x, p2y = polygon[i % n]
            if py > min(p1y, p2y):
                if py <= max(p1y, p2y):
                    if px <= max(p1x, p2x):
                        if p1y != p2y:
                            xinters = (py - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                        if p1x == p2x or px <= xinters:
                            inside = not inside
            p1x, p1y = p2x, p2y
        return inside

    # Render Chevron with glowing vibrant gradient
    for y in range(int(svg_off_y), int(svg_off_y + 40 * svg_scale) + 1):
        for x in range(int(svg_off_x), int(svg_off_x + 40 * svg_scale) + 1):
            if point_in_poly(x, y, poly):
                # Vertical gradient across chevron
                rel_y = (y - (7 * svg_scale + svg_off_y)) / (26 * svg_scale)
                rel_y = max(0.0, min(1.0, rel_y))
                # Top highlight: #FFD54F, Middle: #E5A00D, Bottom: #D47A00
                if rel_y < 0.5:
                    t = rel_y * 2.0
                    cr = int(255 * (1 - t) + 229 * t)
                    cg = int(213 * (1 - t) + 160 * t)
                    cb = int(79 * (1 - t) + 13 * t)
                else:
                    t = (rel_y - 0.5) * 2.0
                    cr = int(229 * (1 - t) + 212 * t)
                    cg = int(160 * (1 - t) + 122 * t)
                    cb = int(13 * (1 - t) + 0 * t)
                blend(x, y, cr, cg, cb, 255)

    # Add sparkling star at top-right of chevron (reclaimed / clean space sparkle)
    def draw_sparkle(sx, sy, rad, r_col, g_col, b_col):
        for y in range(int(sy - rad * 2), int(sy + rad * 2) + 1):
            for x in range(int(sx - rad * 2), int(sx + rad * 2) + 1):
                dx = abs(x - sx)
                dy = abs(y - sy)
                # 4-point star formula
                d_cross = min(dx, dy) + max(dx, dy) * 0.25
                d_dist = math.hypot(dx, dy)
                if d_dist <= rad * 1.8:
                    intensity = max(0.0, 1.0 - (d_cross / rad))
                    if intensity > 0:
                        blend(x, y, r_col, g_col, b_col, int(min(255, intensity * 255)))

    draw_sparkle(cx + W * 0.24, cy - H * 0.22, W * 0.07, 255, 240, 180)
    draw_sparkle(cx - W * 0.26, cy + H * 0.24, W * 0.05, 120, 220, 255)

    # Downsample from 2x supersampling to final size
    final_buf = bytearray(size * size * 4)
    for y in range(size):
        for x in range(size):
            r_acc, g_acc, b_acc, a_acc = 0, 0, 0, 0
            for sy in range(scale):
                for sx in range(scale):
                    idx = ((y * scale + sy) * W + (x * scale + sx)) * 4
                    r_acc += buf[idx + 0]
                    g_acc += buf[idx + 1]
                    b_acc += buf[idx + 2]
                    a_acc += buf[idx + 3]
            count = scale * scale
            f_idx = (y * size + x) * 4
            final_buf[f_idx + 0] = r_acc // count
            final_buf[f_idx + 1] = g_acc // count
            final_buf[f_idx + 2] = b_acc // count
            final_buf[f_idx + 3] = a_acc // count
            
    return bytes(final_buf)

def main():
    target_dir = r"C:\Users\Ron\.gemini\antigravity-ide\scratch\plex-duplicate-finder"
    ico_path = os.path.join(target_dir, "plex_space_saver.ico")
    png_path = os.path.join(target_dir, "plex_space_saver.png")
    
    print("Generating Plex Space Saver logo...")
    sizes = [256, 128, 64, 48, 32, 16]
    ico_entries = []
    
    for s in sizes:
        rgba = render_logo(s)
        png = create_png(s, s, rgba)
        ico_entries.append((s, s, png))
        if s == 256:
            with open(png_path, "wb") as f:
                f.write(png)
            print(f"Saved 256x256 master PNG: {png_path}")
            
    ico_bytes = create_ico(ico_entries)
    with open(ico_path, "wb") as f:
        f.write(ico_bytes)
    print(f"Saved multi-resolution Windows ICO: {ico_path} ({len(ico_bytes)} bytes)")

if __name__ == "__main__":
    main()

