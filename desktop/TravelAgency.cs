using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;

internal sealed class TravelAgency : Form
{
    readonly string root;
    readonly Label status = new Label();
    readonly ComboBox mode = new ComboBox();
    readonly Button start = new Button();
    readonly Button open = new Button();
    readonly Button stop = new Button();
    readonly TextBox endpoint = new TextBox();
    readonly TextBox modelName = new TextBox();
    string localBase = "http://127.0.0.1:1234/v1";
    string localName = "qwen3-8b";
    Process server;
    string url;
    string logPath;
    bool closing;
    int generation;
    readonly object logLock = new object();

    static string ProjectRoot()
    {
        string config = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "project-path.txt");
        if (!File.Exists(config)) throw new Exception("Project configuration is missing. Run Setup again.");
        string path = Path.GetFullPath(File.ReadAllText(config).Trim());
        if (!File.Exists(Path.Combine(path, "app.py")) || !File.Exists(Path.Combine(path, ".venv", "Scripts", "python.exe")))
            throw new Exception("The original project or Python environment was moved. Run Setup and select the Travel_Agency folder.");
        return path;
    }

    [STAThread]
    static int Main(string[] args)
    {
        Application.EnableVisualStyles();
        try
        {
            string project = ProjectRoot();
            if (args.Length > 0 && (args[0] == "--smoke-test" || args[0] == "--smoke-test-local"))
            {
                using (TravelAgency app = new TravelAgency(project))
                {
                    try { app.StartServer(args[0] == "--smoke-test-local"); app.WaitForServer(); File.WriteAllText(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "smoke-test.txt"), "PASS: main app.py returned HTTP 200; mode=" + (args[0] == "--smoke-test-local" ? "local" : "demo") + "; server stopped afterward."); return 0; }
                    finally { app.StopServer(); }
                }
            }
            bool created;
            using (Mutex mutex = new Mutex(true, "Local\\TravelAgencyDesktop-" + Environment.UserName, out created))
            {
                if (!created) { MessageBox.Show("Travel Agency is already running. Open its launcher from the taskbar."); return 0; }
                Application.Run(new TravelAgency(project));
            }
            return 0;
        }
        catch (Exception ex)
        {
            if (args.Length > 0 && args[0].StartsWith("--smoke-test")) File.WriteAllText(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "smoke-test.txt"), "FAIL: " + ex.Message);
            else MessageBox.Show(ex.Message, "Travel Agency", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }

    TravelAgency(string project)
    {
        root = project;
        Text = "Travel Agency";
        ClientSize = new Size(660, 505);
        FormBorderStyle = FormBorderStyle.FixedSingle;
        MaximizeBox = false;
        StartPosition = FormStartPosition.CenterScreen;
        BackColor = Color.FromArgb(245, 247, 252);
        Font = new Font("Segoe UI", 10);
        Controls.Add(new Label { Text = "Travel Agency", Font = new Font("Segoe UI", 25, FontStyle.Bold), Location = new Point(28, 22), Size = new Size(580, 53) });
        Controls.Add(new Label { Text = "Your travel planning workspace", Location = new Point(31, 80), Size = new Size(560, 28) });
        mode.DropDownStyle = ComboBoxStyle.DropDownList;
        mode.Items.AddRange(new object[] { "Demo - sample data, no model calls", "Local LLM - LM Studio" });
        mode.SelectedIndex = 1;
        mode.SetBounds(32, 125, 590, 32);
        Controls.Add(mode);
        Controls.Add(new Label { Text = "Local model server", Location = new Point(32, 170), Size = new Size(170, 25) });
        Controls.Add(new Label { Text = "Model identifier", Location = new Point(32, 210), Size = new Size(170, 25) });
        string settings = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "local-settings.txt");
        if (File.Exists(settings)) { string[] lines = File.ReadAllLines(settings); if (lines.Length == 2) { localBase = lines[0]; localName = lines[1]; } }
        endpoint.Text = localBase; endpoint.SetBounds(205, 167, 417, 30); Controls.Add(endpoint);
        modelName.Text = localName; modelName.SetBounds(205, 207, 417, 30); Controls.Add(modelName);
        Controls.Add(new Label { Text = "Destination, Flights and Money & Customs use the local LLM.\nTravel data APIs may still use the internet. Other sections use sample data.", Location = new Point(32, 257), Size = new Size(590, 52) });
        start.Text = "Start app"; start.SetBounds(32, 335, 170, 42); start.Click += async (s, e) => await Launch(); Controls.Add(start);
        open.Text = "Open window"; open.SetBounds(219, 335, 190, 42); open.Enabled = false; open.Click += (s, e) => OpenWindow(); Controls.Add(open);
        stop.Text = "Stop"; stop.SetBounds(426, 335, 196, 42); stop.Enabled = false; stop.Click += (s, e) => { StopServer(); SetStopped(); }; Controls.Add(stop);
        status.Text = "Ready. Local inference uses no cloud LLM key."; status.SetBounds(32, 394, 590, 47); Controls.Add(status);
        var logs = new LinkLabel { Text = "Open local logs", Location = new Point(32, 460), AutoSize = true };
        logs.LinkClicked += (s, e) => { if (logPath != null) Process.Start("notepad.exe", Quote(logPath)); };
        Controls.Add(logs);
        FormClosing += (s, e) => { closing = true; StopServer(); };
    }

    static string Quote(string value) { return "\"" + value + "\""; }
    static string EdgePath()
    {
        foreach (string baseDir in new[] { Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86), Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData) })
        { string edge = Path.Combine(baseDir, "Microsoft", "Edge", "Application", "msedge.exe"); if (File.Exists(edge)) return edge; }
        throw new Exception("Microsoft Edge is required for the app window. Install Edge and try again.");
    }

    void StartServer(bool live)
    {
        EdgePath();
        var listener = new TcpListener(IPAddress.Loopback, 0);
        listener.Start(); int port = ((IPEndPoint)listener.LocalEndpoint).Port; listener.Stop();
        url = "http://127.0.0.1:" + port;
        string data = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "TravelAgencyDesktop");
        // Smoke testing keeps all artifacts beside the test executable.
        if (Environment.GetCommandLineArgs().Length > 1) data = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "test-data");
        Directory.CreateDirectory(data);
        logPath = Path.Combine(data, "startup-" + DateTime.Now.ToString("yyyyMMdd-HHmmss") + ".log");
        File.WriteAllText(logPath, "Travel Agency startup; mode=" + (live ? "local" : "demo") + Environment.NewLine);
        var info = new ProcessStartInfo(Path.Combine(root, ".venv", "Scripts", "python.exe"), "-u -m chainlit run app.py --host 127.0.0.1 --port " + port + " --headless");
        info.WorkingDirectory = root; info.UseShellExecute = false; info.CreateNoWindow = true;
        info.RedirectStandardOutput = true; info.RedirectStandardError = true;
        info.EnvironmentVariables["TRAVEL_UI_AGENTS"] = "destination=" + (live ? "real" : "dummy") + ",flights=" + (live ? "real" : "dummy") + ",money_customs=" + (live ? "real" : "dummy") + ",restaurants=dummy,activities=dummy,budget=dummy";
        info.EnvironmentVariables["TRAVEL_UI_ORCHESTRATOR"] = "pipeline";
        info.EnvironmentVariables["TRAVEL_LLM_PROVIDER"] = live ? "local" : "";
        info.EnvironmentVariables["TRAVEL_LOCAL_BASE_URL"] = localBase;
        info.EnvironmentVariables["TRAVEL_LOCAL_MODEL"] = localName;
        info.EnvironmentVariables["LANGSMITH_TRACING"] = "false";
        info.EnvironmentVariables["LANGCHAIN_TRACING_V2"] = "false";
        info.EnvironmentVariables["LANGCHAIN_TRACING"] = "false";
        info.EnvironmentVariables["LANGSMITH_API_KEY"] = "";
        info.EnvironmentVariables["LANGCHAIN_API_KEY"] = "";
        info.EnvironmentVariables["ANONYMIZED_TELEMETRY"] = "False";
        info.EnvironmentVariables["PYTHONUTF8"] = "1";
        info.EnvironmentVariables["PYTHONUNBUFFERED"] = "1";
        if (live)
        {
            var prepare = new ProcessStartInfo(info.FileName, "-u -m desktop.local_runtime") { WorkingDirectory = root, UseShellExecute = false, CreateNoWindow = true };
            prepare.EnvironmentVariables["TRAVEL_LOCAL_BASE_URL"] = localBase;
            prepare.EnvironmentVariables["TRAVEL_LOCAL_MODEL"] = localName;
            prepare.RedirectStandardOutput = true; prepare.RedirectStandardError = true;
            using (var preparation = new Process { StartInfo = prepare })
            {
                preparation.OutputDataReceived += Log; preparation.ErrorDataReceived += Log;
                preparation.Start(); preparation.BeginOutputReadLine(); preparation.BeginErrorReadLine();
                if (!preparation.WaitForExit(240000)) { preparation.Kill(); throw new Exception("Local model startup timed out. Check LM Studio and open local logs."); }
                if (preparation.ExitCode != 0) throw new Exception("Could not prepare the local model. Check the model identifier in LM Studio and open local logs. No cloud model was used.");
            }
        }
        if (closing) throw new OperationCanceledException();
        server = new Process { StartInfo = info, EnableRaisingEvents = true };
        server.OutputDataReceived += Log; server.ErrorDataReceived += Log;
        server.Start();
        server.BeginOutputReadLine(); server.BeginErrorReadLine();
    }

    void Log(object sender, DataReceivedEventArgs e)
    {
        if (e.Data == null) return;
        // Provider logs may contain request details; keep diagnostics local.
        lock (logLock) { try { File.AppendAllText(logPath, e.Data + Environment.NewLine); } catch (IOException) { } }
    }

    void WaitForServer()
    {
        Process current = server;
        DateTime deadline = DateTime.UtcNow.AddSeconds(120);
        while (DateTime.UtcNow < deadline)
        {
            if (closing || current != server) throw new OperationCanceledException();
            if (current.HasExited) throw new Exception("The planning service stopped during startup. Open local logs for details.");
            try
            {
                var request = (HttpWebRequest)WebRequest.Create(url + "/");
                request.Proxy = null; request.Timeout = 1500;
                using (var response = (HttpWebResponse)request.GetResponse())
                    if (response.StatusCode == HttpStatusCode.OK) return;
            }
            catch (WebException) { }
            Thread.Sleep(400);
        }
        throw new Exception("Startup timed out. Open local logs, check the project environment, and try again.");
    }

    async Task Launch()
    {
        int attempt = ++generation;
        start.Enabled = false; mode.Enabled = false; endpoint.Enabled = false; modelName.Enabled = false;
        status.Text = "Starting your workspace and loading the local model...";
        try
        {
            bool useLocal = mode.SelectedIndex == 1;
            localBase = endpoint.Text.Trim(); localName = modelName.Text.Trim();
            Uri parsed;
            if (useLocal && (!Uri.TryCreate(localBase, UriKind.Absolute, out parsed) || !parsed.IsLoopback || !localBase.TrimEnd('/').EndsWith("/v1") || String.IsNullOrWhiteSpace(localName))) throw new Exception("Enter a local server URL ending in /v1 and a model identifier.");
            File.WriteAllLines(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "local-settings.txt"), new[] { localBase, localName });
            await Task.Run(() => { StartServer(useLocal); WaitForServer(); });
            if (closing || attempt != generation) return;
            OpenWindow(); open.Enabled = true; stop.Enabled = true;
            status.Text = mode.SelectedIndex == 0 ? "Demo running - results use sample data. Close this launcher to stop." : "Local LLM running - " + localName + ". No cloud LLM fallback.";
        }
        catch (Exception ex)
        {
            StopServer();
            if (!closing) { SetStopped(); MessageBox.Show(ex.Message, "Travel Agency", MessageBoxButtons.OK, MessageBoxIcon.Error); }
        }
    }

    void OpenWindow()
    {
        try
        {
            if (server == null || server.HasExited) throw new Exception("The planning service is stopped. Press Stop, then Start app.");
            string profile = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "TravelAgencyDesktop", "WindowProfile");
            Process.Start(new ProcessStartInfo(EdgePath(), "--app=" + url + " --user-data-dir=" + Quote(profile) + " --no-first-run --no-default-browser-check") { UseShellExecute = false });
        }
        catch (Exception ex) { MessageBox.Show(ex.Message, "Travel Agency"); }
    }

    void SetStopped() { start.Enabled = true; mode.Enabled = true; endpoint.Enabled = true; modelName.Enabled = true; open.Enabled = false; stop.Enabled = false; status.Text = "Stopped. You can choose a mode and start again."; }
    void StopServer()
    {
        generation++;
        Process owned = server; server = null;
        if (owned == null) return;
        try
        {
            if (!owned.HasExited)
            {
                using (var kill = Process.Start(new ProcessStartInfo("taskkill.exe", "/PID " + owned.Id + " /T /F") { UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true, RedirectStandardError = true }))
                    kill.WaitForExit(10000);
                owned.WaitForExit(5000);
            }
        }
        finally { owned.Dispose(); }
    }
}
