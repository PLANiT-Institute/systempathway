import tkinter as tk
from tkinter import filedialog, ttk
import main

class SteelModelGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Steel Model Interface")
        self.root.geometry("600x400")
        
        # Create main frame
        self.main_frame = ttk.Frame(root, padding="10")
        self.main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # File selection
        self.file_frame = ttk.LabelFrame(self.main_frame, text="Input File", padding="5")
        self.file_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        self.file_path = tk.StringVar()
        ttk.Entry(self.file_frame, textvariable=self.file_path, width=50).grid(row=0, column=0, padx=5)
        ttk.Button(self.file_frame, text="Browse", command=self.select_file).grid(row=0, column=1, padx=5)
        
        # Parameters frame
        self.param_frame = ttk.LabelFrame(self.main_frame, text="Model Parameters", padding="5")
        self.param_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        # Solver selection
        ttk.Label(self.param_frame, text="Solver:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.solver_var = tk.StringVar(value="appsi_highs")
        ttk.Combobox(self.param_frame, textvariable=self.solver_var, 
                    values=["appsi_highs", "gurobi", "cplex"], state="readonly").grid(row=0, column=1, sticky=tk.W, pady=2)
        
        # Carbon price checkbox
        self.carbon_price_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.param_frame, text="Include Carbon Price", 
                       variable=self.carbon_price_var).grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=2)
        
        # Max renew entry
        ttk.Label(self.param_frame, text="Max Renew:").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.max_renew_var = tk.StringVar(value="10")
        ttk.Entry(self.param_frame, textvariable=self.max_renew_var, width=10).grid(row=2, column=1, sticky=tk.W, pady=2)
        
        # Allow replace same technology checkbox
        self.replace_tech_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.param_frame, text="Allow Replace Same Technology", 
                       variable=self.replace_tech_var).grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=2)
        
        # Run button
        ttk.Button(self.main_frame, text="Run Model", command=self.run_model).grid(row=2, column=0, columnspan=2, pady=10)
        
        # Status label
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(self.main_frame, textvariable=self.status_var).grid(row=3, column=0, columnspan=2, pady=5)
    
    def select_file(self):
        file_path = filedialog.askopenfilename(
            title="Select Excel File",
            filetypes=[("Excel Files", "*.xlsx *.xls")]
        )
        if file_path:
            self.file_path.set(file_path)
    
    def run_model(self):
        if not self.file_path.get():
            self.status_var.set("Error: Please select an input file")
            return
        
        try:
            self.status_var.set("Running model...")
            self.root.update()
            
            output = main.main(
                self.file_path.get(),
                solver_selection=self.solver_var.get(),
                carboprice_include=self.carbon_price_var.get(),
                max_renew=int(self.max_renew_var.get()),
                allow_replace_same_technology=self.replace_tech_var.get()
            )
            
            self.status_var.set("Model completed successfully!")
            
        except Exception as e:
            self.status_var.set(f"Error: {str(e)}")

def main():
    root = tk.Tk()
    app = SteelModelGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main() 