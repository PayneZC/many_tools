import os
import sys
import subprocess
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import time
import re
import ctypes
from datetime import datetime


def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False


def restart_as_admin():
    ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)


class PortManagerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("端口管理工具")
        self.root.geometry("900x650")
        
        try:
            icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "resources", "port_icon.ico")
            self.root.iconbitmap(icon_path)
        except Exception:
            pass
        
        self.ports_data = []
        self.refresh_thread = None
        self.stop_refresh = threading.Event()
        self.query_thread = None
        self.is_refreshing = False
        self.refresh_lock = threading.Lock()
        
        self.setup_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        
    def setup_ui(self):
        main_frame = ttk.Frame(self.root, padding="15")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        
        title_label = ttk.Label(main_frame, text="端口管理工具", font=("微软雅黑", 16, "bold"))
        title_label.grid(row=0, column=0, columnspan=4, pady=(0, 10))
        
        control_frame = ttk.Frame(main_frame)
        control_frame.grid(row=1, column=0, columnspan=4, sticky=(tk.W, tk.E), pady=(0, 10))
        control_frame.columnconfigure(1, weight=1)
        
        ttk.Label(control_frame, text="端口号:").grid(row=0, column=0, sticky=tk.W, padx=5)
        self.port_entry = ttk.Entry(control_frame, width=15)
        self.port_entry.grid(row=0, column=1, sticky=tk.W, padx=5)
        
        self.search_btn = ttk.Button(control_frame, text="刷新/查询", command=self.search_ports, width=12)
        self.search_btn.grid(row=0, column=2, padx=3, columnspan=2)
        
        auto_frame = ttk.LabelFrame(main_frame, text="自动刷新", padding="10")
        auto_frame.grid(row=2, column=0, columnspan=4, sticky=(tk.W, tk.E), pady=(0, 10))
        
        self.auto_var = tk.BooleanVar(value=False)
        auto_check = ttk.Checkbutton(
            auto_frame, 
            text="启用自动刷新", 
            variable=self.auto_var,
            command=self.toggle_auto_refresh
        )
        auto_check.grid(row=0, column=0, sticky=tk.W)
        
        ttk.Label(auto_frame, text="刷新间隔(秒):").grid(row=0, column=1, sticky=tk.W, padx=(20, 5))
        self.interval_var = tk.IntVar(value=5)
        interval_spin = ttk.Spinbox(auto_frame, from_=2, to=60, textvariable=self.interval_var, width=8)
        interval_spin.grid(row=0, column=2, sticky=tk.W, padx=5)
        
        self.auto_status_label = ttk.Label(auto_frame, text="状态: 已停止", foreground="gray")
        self.auto_status_label.grid(row=0, column=3, sticky=tk.W, padx=(20, 0))
        
        table_frame = ttk.Frame(main_frame)
        table_frame.grid(row=3, column=0, columnspan=4, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)
        
        columns = ("port", "pid", "process_name")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=12)
        
        self.tree.heading("port", text="端口")
        self.tree.heading("pid", text="PID")
        self.tree.heading("process_name", text="进程名称")
        
        self.tree.column("port", width=100, anchor="center")
        self.tree.column("pid", width=100, anchor="center")
        self.tree.column("process_name", width=300, anchor="w")
        
        scrollbar = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
        main_frame.rowconfigure(3, weight=1)
        
        action_frame = ttk.LabelFrame(main_frame, text="操作", padding="10")
        action_frame.grid(row=4, column=0, columnspan=4, sticky=(tk.W, tk.E), pady=(0, 10))
        
        ttk.Button(action_frame, text="释放选中端口", command=self.kill_selected_process, width=15).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="按端口号释放", command=self.kill_by_port_input, width=15).pack(side=tk.LEFT, padx=5)
        
        self.info_label = ttk.Label(
            main_frame, 
            text=f"当前状态: 未查询", 
            font=("微软雅黑", 9),
            foreground="gray"
        )
        self.info_label.grid(row=5, column=0, columnspan=4, sticky=tk.W, pady=(5, 0))
        
        log_frame = ttk.LabelFrame(main_frame, text="操作日志", padding="5")
        log_frame.grid(row=6, column=0, columnspan=4, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(10, 0))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        
        main_frame.rowconfigure(6, weight=1)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, height=8, font=("Consolas", 9))
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        self.log_text.tag_config("info", foreground="black")
        self.log_text.tag_config("success", foreground="green")
        self.log_text.tag_config("error", foreground="red")
        self.log_text.tag_config("warning", foreground="orange")
        
        self.log("欢迎使用端口管理工具", "info")
        self.log("请点击「刷新/查询」查看端口占用情况", "info")
        
    def log(self, message, tag="info"):
        def update():
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.log_text.insert(tk.END, f"[{timestamp}] {message}\n", tag)
            self.log_text.see(tk.END)
        self.root.after(0, update)
        
    def search_ports(self):
        port = self.port_entry.get().strip()
        
        if port:
            if not port.isdigit():
                messagebox.showwarning("警告", "端口号必须是数字")
                return
            
            port_int = int(port)
            if port_int < 1 or port_int > 65535:
                messagebox.showwarning("警告", "端口号必须在1-65535之间")
                return
        
        if self.is_refreshing:
            self.log("正在刷新中，请稍候...", "warning")
            return
        
        self.is_refreshing = True
        self.search_btn.config(state='disabled')
        
        port_hint = f" 正在查询端口 {port}..." if port else " 正在刷新..."
        self.info_label.config(text=f"当前状态:{port_hint}")
        
        self.query_thread = threading.Thread(target=self._do_search, args=(port,), daemon=True)
        self.query_thread.start()
    
    def _do_search(self, port_filter):
        try:
            if port_filter:
                temp_data = self._query_single_port(port_filter)
            else:
                temp_data = self._query_all_ports()
            
            self.root.after(0, lambda: self._update_tree(temp_data, port_filter))
            
        except Exception as e:
            self.root.after(0, lambda: self.log(f"刷新失败: {str(e)}", "error"))
        finally:
            self.root.after(0, self._search_done)
    
    def _search_done(self):
        self.is_refreshing = False
        self.search_btn.config(state='normal')
    
    def _update_tree(self, temp_data, port_filter):
        self.tree.delete(*self.tree.get_children())
        for port, pid, process_name in temp_data:
            self.tree.insert("", tk.END, values=(port, pid, process_name))
        count = len(temp_data)
        
        if port_filter:
            self.info_label.config(text=f"当前状态: 查询端口 {port_filter}，共 {count} 个结果")
            if count > 0:
                self.log(f"查询端口 {port_filter}，共 {count} 个结果", "success")
            else:
                self.log(f"端口 {port_filter} 未被占用", "info")
        else:
            self.info_label.config(text=f"当前状态: 共 {count} 个端口被占用")
            self.log(f"已刷新，共 {count} 个端口被占用", "success")
        
        self.ports_data = temp_data
    
    def _query_all_ports(self):
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True,
            text=True,
            shell=True
        )
        
        if result.returncode != 0:
            return []
        
        port_pattern = re.compile(r'TCP\s+[\d.]+:(\d+)\s+[\d.:]+\s+LISTENING\s+(\d+)')
        udp_pattern = re.compile(r'UDP\s+[\d.]+:(\d+)\s+\*\:\s+(\d+)')
        
        ports_seen = set()
        temp_data = []
        
        for line in result.stdout.split('\n'):
            match = port_pattern.search(line)
            if match:
                port = match.group(1)
                pid = match.group(2)
                
                if port not in ports_seen:
                    ports_seen.add(port)
                    process_name = self._get_process_name(pid)
                    temp_data.append((port, pid, process_name))
            
            match = udp_pattern.search(line)
            if match:
                port = match.group(1)
                pid = match.group(2)
                
                if port not in ports_seen:
                    ports_seen.add(port)
                    process_name = self._get_process_name(pid)
                    temp_data.append((port, pid, process_name))
        
        temp_data.sort(key=lambda x: int(x[0]))
        return temp_data
    
    def _query_single_port(self, port):
        temp_data = []
        ports_seen = set()
        
        try:
            result = subprocess.run(
                f'netstat -ano | findstr ":{port}"',
                capture_output=True,
                text=True,
                shell=True
            )
            
            if result.returncode != 0:
                return temp_data
            
            for line in result.stdout.split('\n'):
                line = line.strip()
                if not line:
                    continue
                
                if 'LISTENING' in line or 'ESTABLISHED' in line or 'UDP' in line:
                    parts = line.split()
                    if len(parts) >= 5:
                        if parts[0] == 'TCP':
                            local_addr = parts[1]
                            if f':{port}' in local_addr:
                                pid = parts[-1]
                                if port not in ports_seen:
                                    ports_seen.add(port)
                                    process_name = self._get_process_name(pid)
                                    temp_data.append((port, pid, process_name))
                        elif parts[0] == 'UDP':
                            local_addr = parts[1]
                            if f':{port}' in local_addr:
                                pid = parts[-1]
                                if port not in ports_seen:
                                    ports_seen.add(port)
                                    process_name = self._get_process_name(pid)
                                    temp_data.append((port, pid, process_name))
            
            return temp_data
        except:
            return temp_data
    
    def refresh_ports(self):
        if self.is_refreshing:
            self.log("正在刷新中，请稍候...", "warning")
            return
        
        self.is_refreshing = True
        self.search_btn.config(state='disabled')
        
        self.query_thread = threading.Thread(target=self._do_refresh, daemon=True)
        self.query_thread.start()
    
    def _do_refresh(self):
        try:
            temp_data = self._query_all_ports()
            
            self.root.after(0, lambda: self._update_tree(temp_data, ""))
            
        except Exception as e:
            self.root.after(0, lambda: self.log(f"刷新失败: {str(e)}", "error"))
        finally:
            self.root.after(0, self._search_done)
    
    def _get_process_name(self, pid):
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                shell=True
            )
            
            if result.returncode == 0 and result.stdout.strip():
                parts = result.stdout.strip().split(',')
                if parts:
                    return parts[0].strip('"')
            
            return f"PID: {pid}"
        except:
            return f"PID: {pid}"
    
    def kill_selected_process(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("警告", "请先选择要释放的端口")
            return
        
        items = self.tree.item(selection[0])['values']
        port = items[0]
        pid = items[1]
        process_name = items[2]
        
        confirm = messagebox.askyesno(
            "确认释放", 
            f"确定要释放端口 {port} 吗？\n这将结束进程: {process_name} (PID: {pid})"
        )
        
        if not confirm:
            return
        
        try:
            result = subprocess.run(
                ["taskkill", "/F", "/PID", str(pid)],
                capture_output=True,
                text=True,
                shell=True
            )
            
            if result.returncode == 0:
                self.log(f"已释放端口 {port} (进程 {process_name})", "success")
                self.refresh_ports()
            else:
                error_msg = result.stderr or result.stdout or "未知错误"
                self.log(f"释放端口失败: {error_msg.strip()}", "error")
                messagebox.showerror("错误", f"释放端口失败: {error_msg.strip()}")
            
        except Exception as e:
            self.log(f"释放端口失败: {str(e)}", "error")
            messagebox.showerror("错误", f"释放端口失败: {str(e)}")
    
    def kill_by_port_input(self):
        port = self.port_entry.get().strip()
        
        if not port:
            messagebox.showwarning("警告", "请在端口号输入框中输入要释放的端口")
            return
        
        if not port.isdigit():
            messagebox.showwarning("警告", "端口号必须是数字")
            return
        
        found = False
        for item in self.tree.get_children():
            values = self.tree.item(item)['values']
            if values and str(values[0]) == port:
                pid = values[1]
                process_name = values[2]
                
                confirm = messagebox.askyesno(
                    "确认释放", 
                    f"确定要释放端口 {port} 吗？\n这将结束进程: {process_name} (PID: {pid})"
                )
                
                if not confirm:
                    return
                
                try:
                    result = subprocess.run(
                        ["taskkill", "/F", "/PID", str(pid)],
                        capture_output=True,
                        text=True,
                        shell=True
                    )
                    
                    if result.returncode == 0:
                        self.log(f"已释放端口 {port} (进程 {process_name})", "success")
                        self.refresh_ports()
                        found = True
                        break
                    else:
                        error_msg = result.stderr or result.stdout or "未知错误"
                        self.log(f"释放端口失败: {error_msg.strip()}", "error")
                        messagebox.showerror("错误", f"释放端口失败: {error_msg.strip()}")
                        return
                except Exception as e:
                    self.log(f"释放端口失败: {str(e)}", "error")
                    messagebox.showerror("错误", f"释放端口失败: {str(e)}")
                    return
                    result = subprocess.run(
                        ["taskkill", "/F", "/PID", str(pid)],
                        capture_output=True,
                        text=True,
                        shell=True
                    )
                    
                    if result.returncode == 0:
                        self.log(f"已释放端口 {port} (进程 {process_name})", "success")
                        self.refresh_ports()
                        found = True
                        break
                    else:
                        error_msg = result.stderr or result.stdout or "未知错误"
                        self.log(f"释放端口失败: {error_msg.strip()}", "error")
                        messagebox.showerror("错误", f"释放端口失败: {error_msg.strip()}")
                        return
        
        if not found:
            self.log(f"端口 {port} 未被占用", "warning")
            messagebox.showinfo("提示", f"端口 {port} 未被占用")
    
    def toggle_auto_refresh(self):
        if self.auto_var.get():
            self.stop_refresh.clear()
            self.refresh_interval = self.interval_var.get()
            self.refresh_thread = threading.Thread(target=self.auto_refresh_loop, daemon=True)
            self.refresh_thread.start()
            self.auto_status_label.config(text=f"状态: 运行中 (每{self.refresh_interval}秒刷新)", foreground="green")
            self.log(f"已启动自动刷新 (每{self.refresh_interval}秒)", "success")
        else:
            self.stop_refresh.set()
            self.auto_status_label.config(text="状态: 已停止", foreground="gray")
            self.log("已停止自动刷新", "info")
    
    def auto_refresh_loop(self):
        while not self.stop_refresh.is_set():
            self.refresh_ports()
            time.sleep(self.refresh_interval)
    
    def on_close(self):
        self.stop_refresh.set()
        self.root.destroy()


def main():
    if not is_admin():
        restart_as_admin()
        sys.exit()
    
    root = tk.Tk()
    app = PortManagerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
