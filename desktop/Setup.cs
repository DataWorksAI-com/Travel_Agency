using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Reflection;
using System.Text;
using System.Windows.Forms;
using Microsoft.Win32;

internal static class Setup
{
    static string SuggestedProject()
    {
        using (var input = new StreamReader(Assembly.GetExecutingAssembly().GetManifestResourceStream("project-path.txt"))) return input.ReadToEnd().Trim();
    }
    static void Extract(string target, string project)
    {
        if (!File.Exists(Path.Combine(project, "app.py")) || !File.Exists(Path.Combine(project, ".venv", "Scripts", "python.exe"))) throw new Exception("Choose the Travel_Agency project folder containing app.py and .venv.");
        Directory.CreateDirectory(target);
        using (var source = Assembly.GetExecutingAssembly().GetManifestResourceStream("TravelAgency.exe"))
        using (var file = File.Create(Path.Combine(target, "TravelAgency.exe"))) source.CopyTo(file);
        File.WriteAllText(Path.Combine(target, "project-path.txt"), Path.GetFullPath(project), Encoding.UTF8);
    }
    static void Shortcut(string path, string exe)
    {
        Type type = Type.GetTypeFromProgID("WScript.Shell");
        dynamic shell = Activator.CreateInstance(type);
        dynamic shortcut = shell.CreateShortcut(path);
        shortcut.TargetPath = exe; shortcut.WorkingDirectory = Path.GetDirectoryName(exe); shortcut.Description = "Travel Agency desktop launcher"; shortcut.Save();
    }
    [STAThread]
    static int Main(string[] args)
    {
        Application.EnableVisualStyles();
        try
        {
            if (args.Length == 2 && args[0] == "--extract-test") { Extract(Path.GetFullPath(args[1]), SuggestedProject()); return 0; }
            using (var form = new Form { Text = "Install Travel Agency", ClientSize = new Size(640, 335), StartPosition = FormStartPosition.CenterScreen, FormBorderStyle = FormBorderStyle.FixedDialog, MaximizeBox = false, Font = new Font("Segoe UI", 10) })
            {
                form.Controls.Add(new Label { Text = "Travel Agency for Windows", Font = new Font("Segoe UI", 21, FontStyle.Bold), Location = new Point(25, 24), Size = new Size(590, 45) });
                form.Controls.Add(new Label { Text = "Install a desktop launcher for this computer.\nKeep your original project and Python environment in place.\nYour API keys stay in the project's local .env file.", Location = new Point(28, 82), Size = new Size(580, 75) });
                form.Controls.Add(new Label { Text = "Project folder", Location = new Point(28, 168), Size = new Size(500, 25) });
                var folder = new TextBox { Text = SuggestedProject(), Location = new Point(28, 198), Size = new Size(485, 30) }; form.Controls.Add(folder);
                var browse = new Button { Text = "Browse", Location = new Point(523, 196), Size = new Size(90, 30) }; form.Controls.Add(browse);
                browse.Click += (s,e) => { using (var dialog = new FolderBrowserDialog()) { dialog.SelectedPath = folder.Text; if (dialog.ShowDialog() == DialogResult.OK) folder.Text = dialog.SelectedPath; } };
                var install = new Button { Text = "Install", Location = new Point(413, 265), Size = new Size(200, 42) }; form.Controls.Add(install);
                install.Click += (s,e) =>
                {
                    try
                    {
                        string target = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", "TravelAgencyDesktop");
                        Extract(target, folder.Text);
                        string exe = Path.Combine(target, "TravelAgency.exe");
                        string startMenu = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Programs), "Travel Agency"); Directory.CreateDirectory(startMenu);
                        Shortcut(Path.Combine(startMenu, "Travel Agency.lnk"), exe);
                        Shortcut(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory), "Travel Agency.lnk"), exe);
                        // The uninstaller only removes this installer's known files and shortcuts.
                        string uninstaller = Path.Combine(target, "Uninstall.ps1");
                        File.WriteAllText(uninstaller, "Add-Type -AssemblyName System.Windows.Forms\r\nif ([System.Windows.Forms.MessageBox]::Show('Uninstall Travel Agency? Close the app first. Your project and keys will be kept.', 'Travel Agency', 'YesNo') -ne 'Yes') { exit }\r\n$installDir = $PSScriptRoot\r\ntry { Remove-Item -LiteralPath (Join-Path $installDir 'TravelAgency.exe') -ErrorAction Stop } catch { [System.Windows.Forms.MessageBox]::Show('Close Travel Agency and try again.'); exit 1 }\r\nRemove-Item -LiteralPath (Join-Path $installDir 'project-path.txt') -ErrorAction SilentlyContinue\r\nRemove-Item -LiteralPath (Join-Path ([Environment]::GetFolderPath('DesktopDirectory')) 'Travel Agency.lnk') -ErrorAction SilentlyContinue\r\n$menuDir = Join-Path ([Environment]::GetFolderPath('Programs')) 'Travel Agency'\r\nRemove-Item -LiteralPath (Join-Path $menuDir 'Travel Agency.lnk') -ErrorAction SilentlyContinue\r\nRemove-Item -LiteralPath $menuDir -ErrorAction SilentlyContinue\r\nRemove-Item -LiteralPath 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\TravelAgencyDesktop' -ErrorAction SilentlyContinue\r\nRemove-Item -LiteralPath (Join-Path $installDir 'Uninstall.ps1') -ErrorAction SilentlyContinue\r\nRemove-Item -LiteralPath $installDir -ErrorAction SilentlyContinue\r\n", Encoding.UTF8);
                        using (var key = Registry.CurrentUser.CreateSubKey(@"Software\Microsoft\Windows\CurrentVersion\Uninstall\TravelAgencyDesktop"))
                        {
                            key.SetValue("DisplayName", "Travel Agency (local project edition)"); key.SetValue("DisplayVersion", "0.2.0"); key.SetValue("Publisher", "Travel Agency Project"); key.SetValue("InstallLocation", target);
                            key.SetValue("UninstallString", "powershell.exe -NoProfile -ExecutionPolicy Bypass -File \"" + uninstaller + "\""); key.SetValue("NoModify", 1); key.SetValue("NoRepair", 1);
                        }
                        MessageBox.Show("Installed. Open Travel Agency from your desktop or Start menu.\nLocal LLM uses LM Studio. Demo uses sample data.", "Travel Agency"); form.Close();
                    }
                    catch (Exception ex) { MessageBox.Show(ex.Message, "Installation failed", MessageBoxButtons.OK, MessageBoxIcon.Error); }
                };
                Application.Run(form);
            }
            return 0;
        }
        catch (Exception ex) { MessageBox.Show(ex.Message, "Travel Agency Setup"); return 1; }
    }
}
