using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Runtime.InteropServices;
using System.Windows.Forms;

internal sealed class StandaloneLauncher : Form
{
    readonly string bundle = AppDomain.CurrentDomain.BaseDirectory;
    readonly string data = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "TravelAgencyStandalone");
    readonly ComboBox mode = new ComboBox();
    readonly Label status = new Label();
    readonly Button start = new Button();
    readonly Button stop = new Button();
    readonly Button open = new Button();
    Process supervisor;
    IntPtr job;
    string url;
    bool closing;

    [STAThread]
    static int Main(string[] args)
    {
        Application.EnableVisualStyles();
        try
        {
            using (var app = new StandaloneLauncher())
            {
                if (args.Length == 1 && args[0] == "--self-test")
                {
                    try { app.Start("cpu", true); app.supervisor.WaitForExit(600000); return app.supervisor.HasExited ? app.supervisor.ExitCode : 1; }
                    finally { app.Stop(); }
                }
                bool unique;
                using (var mutex = new System.Threading.Mutex(true, "Local\\TravelAgencyStandalone-" + Environment.UserName, out unique))
                {
                    if (!unique) { MessageBox.Show("Travel Agency Standalone is already running.", "Travel Agency"); return 0; }
                    Application.Run(app);
                }
            }
            return 0;
        }
        catch (Exception ex) { MessageBox.Show(ex.Message, "Travel Agency", MessageBoxButtons.OK, MessageBoxIcon.Error); return 1; }
    }

    StandaloneLauncher()
    {
        Text = "Travel Agency Standalone"; ClientSize = new Size(660, 365);
        StartPosition = FormStartPosition.CenterScreen; FormBorderStyle = FormBorderStyle.FixedSingle;
        MaximizeBox = false; Font = new Font("Segoe UI", 10); BackColor = Color.FromArgb(245, 247, 252);
        Controls.Add(new Label { Text = "Travel Agency", Font = new Font("Segoe UI", 25, FontStyle.Bold), Location = new Point(28, 20), Size = new Size(590, 55) });
        Controls.Add(new Label { Text = "Standalone edition - Python, local AI and browser included", Location = new Point(32, 80), Size = new Size(590, 30) });
        mode.DropDownStyle = ComboBoxStyle.DropDownList;
        mode.Items.AddRange(new object[] { "Local AI - CPU (works without a dedicated GPU)", "Local AI - GPU (requires a working Vulkan driver)", "Demo - sample data only" });
        mode.SelectedIndex = 0; mode.SetBounds(32, 126, 590, 32); Controls.Add(mode);
        start.Text = "Start app"; start.SetBounds(32, 186, 180, 42); start.Click += (s,e) => { try { Start(new[] { "cpu", "gpu", "demo" }[mode.SelectedIndex], false); } catch (Exception ex) { Stop(); MessageBox.Show(ex.Message, "Travel Agency"); } }; Controls.Add(start);
        open.Text = "Open window"; open.SetBounds(229, 186, 190, 42); open.Enabled = false; open.Click += (s,e) => OpenWindow(); Controls.Add(open);
        stop.Text = "Stop"; stop.SetBounds(436, 186, 186, 42); stop.Enabled = false; stop.Click += (s,e) => Stop(); Controls.Add(stop);
        status.Text = "Ready. First startup loads the bundled model into memory."; status.SetBounds(32, 250, 590, 45); Controls.Add(status);
        var settings = new LinkLabel { Text = "Optional data API settings", Location = new Point(32, 320), AutoSize = true }; settings.LinkClicked += (s,e) => OpenSettings(); Controls.Add(settings);
        var logs = new LinkLabel { Text = "Open logs", Location = new Point(470, 320), AutoSize = true }; logs.LinkClicked += (s,e) => { Directory.CreateDirectory(data); Process.Start("explorer.exe", Quote(data)); }; Controls.Add(logs);
        FormClosing += (s,e) => { closing = true; Stop(); };
    }

    static string Quote(string text) { return "\"" + text + "\""; }
    void Start(string selected, bool test)
    {
        foreach (var relative in new[] { "runtime\\python.exe", "app\\app.py", "models\\Qwen3-8B-Q4_K_M.gguf", "engine\\cpu\\llama-server.exe", "browser\\firefox\\firefox.exe" })
            if (!File.Exists(Path.Combine(bundle, relative))) throw new Exception("An installed component is missing. Run the full installer again: " + relative);
        Directory.CreateDirectory(data);
        var info = new ProcessStartInfo(Path.Combine(bundle, "runtime", "python.exe"), "-I -u " + Quote(Path.Combine(bundle, "app", "desktop", "standalone_runtime.py")) + " --mode " + selected + (test ? " --self-test" : ""));
        info.WorkingDirectory = Path.Combine(bundle, "app"); info.UseShellExecute = false; info.CreateNoWindow = true;
        info.RedirectStandardOutput = true; info.RedirectStandardError = true;
        if (test) { info.EnvironmentVariables["TRAVEL_STANDALONE_DATA"] = Path.Combine(bundle, "self-test-data"); info.EnvironmentVariables["TRAVEL_OFFLINE_TEST"] = "1"; }
        job = CreateJobObject(IntPtr.Zero, null);
        var limits = new ExtendedLimits(); limits.Basic.LimitFlags = 0x2000;
        int size = Marshal.SizeOf(limits); IntPtr memory = Marshal.AllocHGlobal(size);
        try { Marshal.StructureToPtr(limits, memory, false); if (job == IntPtr.Zero || !SetInformationJobObject(job, 9, memory, (uint)size)) throw new Exception("Could not create the service cleanup job."); }
        finally { Marshal.FreeHGlobal(memory); }
        supervisor = new Process { StartInfo = info, EnableRaisingEvents = true };
        supervisor.OutputDataReceived += (s,e) => UpdateStatus(e.Data);
        supervisor.ErrorDataReceived += (s,e) => { if (e.Data != null) File.AppendAllText(Path.Combine(data, "launcher.log"), e.Data + Environment.NewLine); };
        supervisor.Start();
        if (!AssignProcessToJobObject(job, supervisor.Handle)) { supervisor.Kill(); throw new Exception("Could not supervise the bundled services."); }
        supervisor.BeginOutputReadLine(); supervisor.BeginErrorReadLine();
        if (!test) { start.Enabled = false; mode.Enabled = false; stop.Enabled = true; status.Text = "Starting bundled Python and local AI. Please wait..."; }
    }

    void UpdateStatus(string line)
    {
        if (line == null) return;
        File.AppendAllText(Path.Combine(data, "launcher.log"), line + Environment.NewLine);
        if (closing || !IsHandleCreated) return;
        BeginInvoke((Action)(() =>
        {
            if (line.StartsWith("READY ")) { url = line.Substring(6).Trim(); status.Text = "Running. Model inference stays on this computer."; open.Enabled = true; }
            else if (line.StartsWith("STATUS ")) status.Text = line.Substring(7);
            else if (line.StartsWith("ERROR ")) { status.Text = line.Substring(6); Stop(); status.Text = line.Substring(6); }
        }));
    }

    void OpenWindow()
    {
        if (String.IsNullOrEmpty(url)) return;
        Directory.CreateDirectory(Path.Combine(data, "browser"));
        Process.Start(new ProcessStartInfo(Path.Combine(bundle, "browser", "firefox", "firefox.exe"), "-no-remote -profile " + Quote(Path.Combine(data, "browser")) + " -new-window " + url) { UseShellExecute = false });
    }

    void OpenSettings()
    {
        Directory.CreateDirectory(data); string path = Path.Combine(data, "data-services.env");
        if (!File.Exists(path)) File.WriteAllText(path, "# Optional travel-data API credentials; no LLM key required.\r\nGEOAPIFY_API_KEY=\r\nTRAVELPAYOUTS_TOKEN=\r\nGOOGLE_ROUTES_API_KEY=\r\n");
        Process.Start("notepad.exe", Quote(path));
    }

    void Stop()
    {
        // Closing the job terminates only this launcher's owned Python,
        // model-server and browser process tree, including on launcher exit.
        if (job != IntPtr.Zero) { CloseHandle(job); job = IntPtr.Zero; }
        if (supervisor != null) { try { supervisor.WaitForExit(10000); } catch (InvalidOperationException) { } supervisor.Dispose(); supervisor = null; }
        if (!closing) { start.Enabled = true; mode.Enabled = true; open.Enabled = false; stop.Enabled = false; status.Text = "Stopped. Choose a mode and start again."; }
    }

    [StructLayout(LayoutKind.Sequential)] struct BasicLimits { public long PerProcessUserTimeLimit, PerJobUserTimeLimit; public uint LimitFlags; public UIntPtr MinimumWorkingSetSize, MaximumWorkingSetSize; public uint ActiveProcessLimit; public UIntPtr Affinity; public uint PriorityClass, SchedulingClass; }
    [StructLayout(LayoutKind.Sequential)] struct IoCounters { public ulong ReadOperationCount, WriteOperationCount, OtherOperationCount, ReadTransferCount, WriteTransferCount, OtherTransferCount; }
    [StructLayout(LayoutKind.Sequential)] struct ExtendedLimits { public BasicLimits Basic; public IoCounters Io; public UIntPtr ProcessMemoryLimit, JobMemoryLimit, PeakProcessMemoryUsed, PeakJobMemoryUsed; }
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)] static extern IntPtr CreateJobObject(IntPtr attributes, string name);
    [DllImport("kernel32.dll")] static extern bool SetInformationJobObject(IntPtr job, int type, IntPtr info, uint length);
    [DllImport("kernel32.dll")] static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);
    [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr handle);
}
