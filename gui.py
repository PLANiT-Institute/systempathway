import tkinter as tk
from tkinter import filedialog, ttk, messagebox
import main
import os
import subprocess

class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tooltip = None
        self.widget.bind("<Enter>", self.show)
        self.widget.bind("<Leave>", self.hide)

    def show(self, event=None):
        x, y, _, _ = self.widget.bbox("insert")
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 25
        self.tooltip = tk.Toplevel(self.widget)
        self.tooltip.wm_overrideredirect(True)
        self.tooltip.wm_geometry(f"+{x}+{y}")
        label = tk.Label(self.tooltip, text=self.text, justify=tk.LEFT,
                        background="#ffffe0", relief=tk.SOLID, borderwidth=1)
        label.pack()

    def hide(self, event=None):
        if self.tooltip:
            self.tooltip.destroy()
            self.tooltip = None

class SteelModelGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Steel Model Interface")
        self.root.geometry("700x500")
        
        # Create main frame with scrollbar
        self.main_frame = ttk.Frame(root)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Create canvas and scrollbar
        self.canvas = tk.Canvas(self.main_frame)
        self.scrollbar = ttk.Scrollbar(self.main_frame, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        
        # File selection
        self.file_frame = ttk.LabelFrame(self.scrollable_frame, text="Input File", padding="5")
        self.file_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        self.file_path = tk.StringVar()
        self.file_entry = ttk.Entry(self.file_frame, textvariable=self.file_path, width=50)
        self.file_entry.grid(row=0, column=0, padx=5)
        ToolTip(self.file_entry, "Select the input Excel file containing the model data")
        
        ttk.Button(self.file_frame, text="Browse", command=self.select_file).grid(row=0, column=1, padx=5)
        
        # Parameters frame
        self.param_frame = ttk.LabelFrame(self.scrollable_frame, text="Model Parameters", padding="5")
        self.param_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        # Solver selection
        ttk.Label(self.param_frame, text="Solver:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.solver_var = tk.StringVar(value="appsi_highs")
        self.solver_combo = ttk.Combobox(self.param_frame, textvariable=self.solver_var, 
                    values=["appsi_highs", "gurobi", "cplex"], state="readonly")
        self.solver_combo.grid(row=0, column=1, sticky=tk.W, pady=2)
        ToolTip(self.solver_combo, "Select the optimization solver to use")
        
        # Carbon price checkbox
        self.carbon_price_var = tk.BooleanVar(value=False)
        self.carbon_price_check = ttk.Checkbutton(self.param_frame, text="Include Carbon Price", 
                       variable=self.carbon_price_var)
        self.carbon_price_check.grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=2)
        ToolTip(self.carbon_price_check, "Include carbon price in the model calculations")
        
        # Max renew entry
        ttk.Label(self.param_frame, text="Max Renew:").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.max_renew_var = tk.StringVar(value="10")
        self.max_renew_entry = ttk.Entry(self.param_frame, textvariable=self.max_renew_var, width=10)
        self.max_renew_entry.grid(row=2, column=1, sticky=tk.W, pady=2)
        ToolTip(self.max_renew_entry, "Maximum number of renewals allowed (must be a positive integer)")
        
        # Allow replace same technology checkbox
        self.replace_tech_var = tk.BooleanVar(value=False)
        self.replace_tech_check = ttk.Checkbutton(self.param_frame, text="Allow Replace Same Technology", 
                       variable=self.replace_tech_var)
        self.replace_tech_check.grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=2)
        ToolTip(self.replace_tech_check, "Allow replacing a technology with the same type")
        
        # Progress bar
        self.progress_frame = ttk.Frame(self.scrollable_frame)
        self.progress_frame.grid(row=2, column=0, columnspan=2, pady=10)
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(self.progress_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill=tk.X, expand=True)
        
        # Buttons frame
        self.button_frame = ttk.Frame(self.scrollable_frame)
        self.button_frame.grid(row=3, column=0, columnspan=2, pady=10)
        
        # Run button
        self.run_button = ttk.Button(self.button_frame, text="Run Model", command=self.run_model)
        self.run_button.pack(side=tk.LEFT, padx=5)
        
        # Open results button
        self.open_results_button = ttk.Button(self.button_frame, text="Open Results Folder", 
                                            command=self.open_results_folder, state=tk.DISABLED)
        self.open_results_button.pack(side=tk.LEFT, padx=5)
        
        # Status label
        self.status_var = tk.StringVar(value="Ready")
        self.status_label = ttk.Label(self.scrollable_frame, textvariable=self.status_var)
        self.status_label.grid(row=4, column=0, columnspan=2, pady=5)
        
        # Configure grid weights
        self.scrollable_frame.columnconfigure(0, weight=1)
        self.scrollable_frame.columnconfigure(1, weight=1)
    
    def select_file(self):
        file_path = filedialog.askopenfilename(
            title="Select Excel File",
            filetypes=[("Excel Files", "*.xlsx *.xls")]
        )
        if file_path:
            self.file_path.set(file_path)
            self.open_results_button.config(state=tk.NORMAL)
    
    def validate_max_renew(self):
        try:
            value = int(self.max_renew_var.get())
            if value <= 0:
                raise ValueError("Max renew must be positive")
            return True
        except ValueError as e:
            messagebox.showerror("Input Error", str(e))
            return False
    
    def open_results_folder(self):
        results_path = os.path.join(os.path.dirname(self.file_path.get()), "results")
        if os.path.exists(results_path):
            if os.name == 'nt':  # Windows
                os.startfile(results_path)
            else:  # macOS and Linux
                subprocess.run(['open', results_path] if os.name == 'posix' else ['xdg-open', results_path])
        else:
            messagebox.showinfo("Info", "Results folder does not exist yet. Run the model first.")
    
    def run_model(self):
        if not self.file_path.get():
            self.status_var.set("Error: Please select an input file")
            return
        
        if not self.validate_max_renew():
            return
        
        try:
            self.status_var.set("Running model...")
            self.progress_var.set(0)
            self.run_button.config(state=tk.DISABLED)
            self.root.update()
            
            # Simulate progress (you can replace this with actual progress updates)
            for i in range(5):
                self.progress_var.set(i * 20)
                self.root.update()
                self.root.after(500)  # Simulate work
            
            output = main.main(
                self.file_path.get(),
                solver_selection=self.solver_var.get(),
                carboprice_include=self.carbon_price_var.get(),
                max_renew=int(self.max_renew_var.get()),
                allow_replace_same_technology=self.replace_tech_var.get()
            )
            
            self.progress_var.set(100)
            self.status_var.set("Model completed successfully!")
            self.open_results_button.config(state=tk.NORMAL)
            
        except Exception as e:
            self.status_var.set(f"Error: {str(e)}")
            messagebox.showerror("Error", str(e))
        finally:
            self.run_button.config(state=tk.NORMAL)

def main():
    root = tk.Tk()
    app = SteelModelGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main() 