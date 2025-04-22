// Place this in static/js/expenses.js

/**
 * Handles complex calculations and data processing for the expenses page
 */
class ExpensesManager {
    constructor() {
        // Store references to DOM elements
        this.monthFilter = document.getElementById('month-filter');
        this.buildingFilter = document.getElementById('building-filter');
        this.saveBtn = document.getElementById('save-btn');
        this.exportBtn = document.getElementById('export-btn');
        this.reloadBtn = document.getElementById('reload-btn');
        this.expensesData = document.getElementById('expenses-data');
        this.loadingOverlay = document.querySelector('.loading-overlay');
        this.saveMessage = document.getElementById('save-message');

        // Data state
        this.currentUnits = [];
        this.currentExpenses = {};

        // Initialize
        this.init();
    }

    /**
     * Initialize the expense manager
     */
    init() {
        // Set default month if not set
        if (!this.monthFilter.value) {
            const now = new Date();
            const year = now.getFullYear();
            const month = String(now.getMonth() + 1).padStart(2, '0');
            this.monthFilter.value = `${year}-${month}`;
        }

        // Set up event listeners
        this.setupEventListeners();

        // Load initial data
        this.loadExpensesData();
    }

    /**
     * Set up all event listeners
     */
    setupEventListeners() {
        this.monthFilter.addEventListener('change', () => this.loadExpensesData());
        this.buildingFilter.addEventListener('change', () => this.filterUnits());
        this.saveBtn.addEventListener('click', () => this.saveExpensesData());
        this.exportBtn.addEventListener('click', () => this.exportToCsv());
        this.reloadBtn.addEventListener('click', () => this.loadExpensesData());

        // Add the sales from bookings button listener
        const loadSalesBtn = document.getElementById('load-sales-btn');
        if (loadSalesBtn) {
          loadSalesBtn.addEventListener('click', () => {
            const [year, month] = this.monthFilter.value.split('-');
            this.loadSalesFromBookings(year, month);
          });
        }

        // Add the repair costs from issues button listener
        const loadRepairBtn = document.getElementById('load-repair-btn');
        if (loadRepairBtn) {
          loadRepairBtn.addEventListener('click', () => {
            const [year, month] = this.monthFilter.value.split('-');
            this.loadRepairCostsFromIssues(year, month);
          });
        }

        // Add the replace costs from issues button listener
        const loadReplaceBtn = document.getElementById('load-replace-btn');
        if (loadReplaceBtn) {
          loadReplaceBtn.addEventListener('click', () => {
            const [year, month] = this.monthFilter.value.split('-');
            this.loadReplaceCostsFromIssues(year, month);
          });
        }
    }

    /**
     * Load expenses data from the server
     */
    loadExpensesData() {
        this.showLoading(true);

        // Get selected month-year
        const [year, month] = this.monthFilter.value.split('-');

        // Make API request to get expense data
        fetch(`/api/expenses?year=${year}&month=${month}`)
            .then(response => response.json())
            .then(data => {
                // Store data
                this.currentUnits = data.units || [];
                this.currentExpenses = data.expenses || {};

                // Add any _formula fields from your server response if available
                for (const unitId in this.currentExpenses) {
                    // Check if there are formula fields in the response
                    for (const field in this.currentExpenses[unitId]) {
                        if (field.endsWith('_formula')) {
                            const baseField = field.replace('_formula', '');
                            // Attach formula data attribute to input when rendering
                            // We'll use this in the renderExpensesTable function
                        }
                    }
                }

                // Render table
                this.renderExpensesTable();

                // Apply any active filters
                this.filterUnits();

                this.showLoading(false);
            })
            .catch(error => {
                console.error('Error loading expenses data:', error);

                // If API fails, generate empty data for all units
                fetch('/api/get_units')
                    .then(response => response.json())
                    .then(units => {
                        this.currentUnits = units;
                        this.currentExpenses = {};

                        // Render empty table
                        this.renderExpensesTable();

                        // Apply any active filters
                        this.filterUnits();

                        this.showLoading(false);
                    })
                    .catch(err => {
                        console.error('Failed to load units:', err);
                        this.showLoading(false);
                        this.showSaveMessage('Failed to load data. Please try again.', true);
                    });
            });
    }

    /**
     * Render the expenses table with current data
     */
    renderExpensesTable() {
        // Clear table
        this.expensesData.innerHTML = '';

        // Add row for each unit
        this.currentUnits.forEach(unit => {
            const unitId = unit.id;
            const unitExpense = this.currentExpenses[unitId] || {
                sales: '',
                rental: '',
                electricity: '',
                water: '',
                sewage: '',
                internet: '',
                cleaner: '',
                laundry: '',
                supplies: '',
                repair: '',
                replace: '',
                other: ''
            };

            // Calculate net earn
            const netEarn = this.calculateNetEarn(unitExpense);

            // Create row
            const row = document.createElement('tr');
            row.dataset.unitId = unitId;
            row.dataset.building = unit.building || '';

            // Unit column
            const unitCell = document.createElement('td');
            unitCell.className = 'unit-column';
            unitCell.textContent = unit.unit_number;
            row.appendChild(unitCell);

            // Expense columns
            const expenseColumns = [
                'sales', 'rental', 'electricity', 'water', 'sewage',
                'internet', 'cleaner', 'laundry', 'supplies',
                'repair', 'replace', 'other'
            ];

            expenseColumns.forEach(column => {
                const cell = document.createElement('td');
                cell.className = 'editable';

                const input = document.createElement('input');
                input.type = 'text';
                input.value = unitExpense[column] || '';
                input.dataset.column = column;
                input.dataset.unitId = unitId;

                // Check if there's a stored formula for this field
                const formulaField = `${column}_formula`;
                if (this.currentExpenses[unitId] && this.currentExpenses[unitId][formulaField]) {
                    input.dataset.formula = this.currentExpenses[unitId][formulaField];
                }

                // Auto-calculate on input change
                input.addEventListener('input', (e) => {
                    // Update currentExpenses object
                    if (!this.currentExpenses[unitId]) {
                        this.currentExpenses[unitId] = {};
                    }
                    this.currentExpenses[unitId][column] = e.target.value;

                    // Recalculate net earn
                    this.updateNetEarn(unitId);
                });

                // Add focus event to show formula if exists
                input.addEventListener('focus', function() {
                    // When the cell is focused, show the original formula if it exists
                    if (this.dataset.formula) {
                        // Store the display value (calculated result) as a data attribute
                        this.dataset.displayValue = this.value;

                        // Show the original formula for editing
                        this.value = this.dataset.formula;
                    }
                });

                // Add blur event for formula calculation
                input.addEventListener('blur', (e) => {
                    const value = e.target.value.trim();

                    // Check if it's a formula (starts with =)
                    if (value && value.startsWith('=')) {
                        try {
                            // Store the original formula
                            e.target.dataset.formula = value;

                            // Calculate the result
                            const formulaExpression = value.substring(1); // Remove the = sign

                            // Replace any commas with empty strings before evaluating
                            const result = this.calculateFormula(formulaExpression.replace(/,/g, ''));

                            // Show the calculated result
                            e.target.value = result;

                            // Update the expenses data
                            if (!this.currentExpenses[unitId]) {
                                this.currentExpenses[unitId] = {};
                            }
                            this.currentExpenses[unitId][column] = result;
                            // Also store the formula
                            this.currentExpenses[unitId][`${column}_formula`] = value;

                            // Recalculate net earn
                            this.updateNetEarn(unitId);
                        } catch (error) {
                            // Show error styling
                            e.target.classList.add('calculation-error');
                            setTimeout(() => {
                                e.target.classList.remove('calculation-error');
                            }, 2000);
                        }
                    } else if (value && value.match(/[-+*/()]/)) {
                        // If it contains math operators but doesn't start with =, evaluate it directly
                        try {
                            // Remove any formula data if exists
                            if (e.target.dataset.formula) {
                                delete e.target.dataset.formula;
                            }

                            const result = this.calculateFormula(value.replace(/,/g, ''));
                            e.target.value = result;

                            // Update data
                            if (!this.currentExpenses[unitId]) {
                                this.currentExpenses[unitId] = {};
                            }
                            this.currentExpenses[unitId][column] = result;

                            // Remove formula storage if exists
                            if (this.currentExpenses[unitId][`${column}_formula`]) {
                                delete this.currentExpenses[unitId][`${column}_formula`];
                            }

                            // Recalculate net earn
                            this.updateNetEarn(unitId);
                        } catch (error) {
                            e.target.classList.add('calculation-error');
                            setTimeout(() => {
                                e.target.classList.remove('calculation-error');
                            }, 2000);
                        }
                    }
                });

                cell.appendChild(input);
                row.appendChild(cell);
            });

            // Net earn column
            const netEarnCell = document.createElement('td');
            netEarnCell.className = 'net-earn';
            netEarnCell.id = `net-earn-${unitId}`;
            netEarnCell.textContent = netEarn;
            if (parseFloat(netEarn) < 0) {
                netEarnCell.classList.add('negative');
            } else {
                netEarnCell.classList.add('positive');
            }
            row.appendChild(netEarnCell);

            // Add row to table
            this.expensesData.appendChild(row);
        });
    }

    /**
     * Filter units by building
     */
    filterUnits() {
        const building = this.buildingFilter.value;

        const rows = this.expensesData.querySelectorAll('tr');
        rows.forEach(row => {
            if (building === 'all' || row.dataset.building === building) {
                row.style.display = '';
            } else {
                row.style.display = 'none';
            }
        });
    }

    /**
     * Calculate net earn for a unit's expenses
     * @param {Object} expense - The expense data object
     * @returns {string} - The calculated net earn as a formatted string
     */
    calculateNetEarn(expense) {
        // Get numeric values, defaulting to 0 if empty or NaN
        const getValue = (value) => {
            if (!value) return 0;

            // If it's a formula (check formula field), use the calculated value
            const num = parseFloat(value.toString().replace(/,/g, ''));
            return isNaN(num) ? 0 : num;
        };

        const sales = getValue(expense.sales);
        const rental = getValue(expense.rental);
        const electricity = getValue(expense.electricity);
        const water = getValue(expense.water);
        const sewage = getValue(expense.sewage);
        const internet = getValue(expense.internet);
        const cleaner = getValue(expense.cleaner);
        const laundry = getValue(expense.laundry);
        const supplies = getValue(expense.supplies);
        const repair = getValue(expense.repair);
        const replace = getValue(expense.replace);
        const other = getValue(expense.other);

        // Calculate net earn
        const netEarn = sales - rental - electricity - water - sewage -
                        internet - cleaner - laundry - supplies -
                        repair - replace - other;

        return netEarn.toFixed(2);
    }

    /**
     * Update the net earn cell for a unit
     * @param {string|number} unitId - The unit ID
     */
    updateNetEarn(unitId) {
        const expense = this.currentExpenses[unitId] || {};
        const netEarn = this.calculateNetEarn(expense);

        const netEarnCell = document.getElementById(`net-earn-${unitId}`);
        if (netEarnCell) {
            netEarnCell.textContent = netEarn;

            // Update color
            netEarnCell.classList.remove('positive', 'negative');
            if (parseFloat(netEarn) < 0) {
                netEarnCell.classList.add('negative');
            } else {
                netEarnCell.classList.add('positive');
            }
        }
    }

    /**
     * Save expenses data to the server
     */
    saveExpensesData() {
        this.showLoading(true);

        // Get selected month-year
        const [year, month] = this.monthFilter.value.split('-');

        // Prepare data for saving
        const data = {
            year: year,
            month: month,
            expenses: {}
        };

        // Create a deep copy of the expenses object
        for (const unitId in this.currentExpenses) {
            data.expenses[unitId] = {};

            // Copy each expense field, including formula fields
            for (const field in this.currentExpenses[unitId]) {
                data.expenses[unitId][field] = this.currentExpenses[unitId][field];
            }
        }

        // Make API request to save data
        fetch('/api/expenses', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(data)
        })
        .then(response => {
            if (!response.ok) {
                throw new Error('Failed to save data');
            }
            return response.json();
        })
        .then(result => {
            this.showLoading(false);
            this.showSaveMessage('Data saved successfully');
        })
        .catch(error => {
            console.error('Error saving expenses data:', error);
            this.showLoading(false);
            this.showSaveMessage('Failed to save data. Please try again.', true);
        });
    }

    /**
     * Export expenses data to CSV
     */
    exportToCsv() {
        // Create CSV content
        let csvContent = 'Unit,Sales,Rental,Electricity,Water,Sewage,Internet,Cleaner,Laundry,Supplies,Repair,Replace,Other,Net Earn\n';

        // Add data rows
        const rows = this.expensesData.querySelectorAll('tr');
        rows.forEach(row => {
            // Skip hidden rows (filtered out)
            if (row.style.display === 'none') return;

            const unitId = row.dataset.unitId;
            const unitName = row.querySelector('.unit-column').textContent;
            const expense = this.currentExpenses[unitId] || {};

            // Get values for all columns
            const values = [
                unitName,
                expense.sales || '',
                expense.rental || '',
                expense.electricity || '',
                expense.water || '',
                expense.sewage || '',
                expense.internet || '',
                expense.cleaner || '',
                expense.laundry || '',
                expense.supplies || '',
                expense.repair || '',
                expense.replace || '',
                expense.other || '',
                this.calculateNetEarn(expense)
            ];

            // Add row to CSV
            csvContent += values.map(value => `"${value}"`).join(',') + '\n';
        });

        // Create download link
        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.setAttribute('href', url);
        link.setAttribute('download', `PropertyHub_Expenses_${this.monthFilter.value}.csv`);
        link.style.visibility = 'hidden';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    }

    /**
     * Show/hide loading overlay
     * @param {boolean} show - Whether to show or hide the overlay
     */
    showLoading(show) {
        this.loadingOverlay.style.display = show ? 'flex' : 'none';
    }

    /**
     * Show save message
     * @param {string} message - The message to display
     * @param {boolean} isError - Whether this is an error message
     */
    showSaveMessage(message, isError = false) {
        this.saveMessage.textContent = message;
        this.saveMessage.classList.toggle('error', isError);
        this.saveMessage.classList.add('show');

        setTimeout(() => {
            this.saveMessage.classList.remove('show');
        }, 3000);
    }

    /**
     * Helper function to calculate formula values
     * @param {string} expression - The formula expression to calculate
     * @returns {string} - The calculated result formatted as a string
     */
    calculateFormula(expression) {
        if (!expression) return '';

        // Clean up the expression
        let cleanExpression = expression.replace(/\+{2,}/g, '+')
                                     .replace(/\-{2,}/g, '-')
                                     .replace(/\*{2,}/g, '*')
                                     .replace(/\/{2,}/g, '/');

        // Replace mixed operations
        cleanExpression = cleanExpression.replace(/\+\-/g, '-')
                                       .replace(/\-\+/g, '-')
                                       .replace(/\-\-/g, '+');

        // Validate expression
        if (/[^0-9\+\-\*\/\.\(\)\s]/.test(cleanExpression)) {
            throw new Error('Invalid characters in expression');
        }

        // Evaluate and return the formatted result
        try {
            const result = Function(`'use strict'; return (${cleanExpression})`)();
            return parseFloat(result).toFixed(2);
        } catch (e) {
            console.error('Error evaluating formula:', e, expression);
            throw e;
        }
    }

    /**
     * Load sales data from bookings
     * @param {string|number} year - The year to load data for
     * @param {string|number} month - The month to load data for
     */
    loadSalesFromBookings(year, month) {
        this.showLoading(true);

        // Make API request to get booking data for sales calculations
        fetch(`/api/bookings/monthly_revenue?year=${year}&month=${month}`)
            .then(response => response.json())
            .then(data => {
                // Loop through the units and update their sales values from bookings
                for (const unitId in data.revenues) {
                    if (this.currentExpenses[unitId]) {
                        this.currentExpenses[unitId].sales = data.revenues[unitId].toFixed(2);
                    } else {
                        this.currentExpenses[unitId] = {
                            sales: data.revenues[unitId].toFixed(2),
                            rental: '',
                            electricity: '',
                            water: '',
                            sewage: '',
                            internet: '',
                            cleaner: '',
                            laundry: '',
                            supplies: '',
                            repair: '',
                            replace: '',
                            other: ''
                        };
                    }

                    // Update the net earn display
                    this.updateNetEarn(unitId);
                }

                // Update the UI with new values
                this.renderExpensesTable();
                this.showLoading(false);
            })
            .catch(error => {
                console.error('Error loading booking revenues:', error);
                this.showLoading(false);
                this.showSaveMessage('Failed to load booking revenues. Please try again.', true);
            });
    }

    /**
     * Load repair costs from issues
     * @param {string|number} year - The year to load data for
     * @param {string|number} month - The month to load data for
     */
    loadRepairCostsFromIssues(year, month) {
        this.showLoading(true);

        // Make API request to get issue costs for repair calculations
        fetch(`/api/issues/monthly_costs?year=${year}&month=${month}&type=repair`)
            .then(response => response.json())
            .then(data => {
                // Loop through the units and update their repair values from issues
                for (const unitId in data.costs) {
                    if (this.currentExpenses[unitId]) {
                        this.currentExpenses[unitId].repair = data.costs[unitId].toFixed(2);
                    } else {
                        this.currentExpenses[unitId] = {
                            sales: '',
                            rental: '',
                            electricity: '',
                            water: '',
                            sewage: '',
                            internet: '',
                            cleaner: '',
                            laundry: '',
                            supplies: '',
                            repair: data.costs[unitId].toFixed(2),
                            replace: '',
                            other: ''
                        };
                    }

                    // Update the net earn display
                    this.updateNetEarn(unitId);
                }

                // Update the UI with new values
                this.renderExpensesTable();
                this.showLoading(false);
            })
            .catch(error => {
                console.error('Error loading issue repair costs:', error);
                this.showLoading(false);
                this.showSaveMessage('Failed to load repair costs. Please try again.', true);
            });
    }

    /**
     * Load replacement costs from issues
     * @param {string|number} year - The year to load data for
     * @param {string|number} month - The month to load data for
     */
    loadReplaceCostsFromIssues(year, month) {
        this.showLoading(true);

        // Make API request to get issue costs for replacement calculations
        fetch(`/api/issues/monthly_costs?year=${year}&month=${month}&type=replace`)
            .then(response => response.json())
            .then(data => {
                // Loop through the units and update their replace values from issues
                for (const unitId in data.costs) {
                    if (this.currentExpenses[unitId]) {
                        this.currentExpenses[unitId].replace = data.costs[unitId].toFixed(2);
                    } else {
                        this.currentExpenses[unitId] = {
                            sales: '',
                            rental: '',
                            electricity: '',
                            water: '',
                            sewage: '',
                            internet: '',
                            cleaner: '',
                            laundry: '',
                            supplies: '',
                            repair: '',
                            replace: data.costs[unitId].toFixed(2),
                            other: ''
                        };
                    }

                    // Update the net earn display
                    this.updateNetEarn(unitId);
                }

                // Update the UI with new values
                this.renderExpensesTable();
                this.showLoading(false);
            })
            .catch(error => {
                console.error('Error loading issue replacement costs:', error);
                this.showLoading(false);
                this.showSaveMessage('Failed to load replacement costs. Please try again.', true);
            });
    }
}

// Initialize the expenses manager when the page loads
document.addEventListener('DOMContentLoaded', function() {
    if (document.getElementById('expenses-table')) {
        window.expensesManager = new ExpensesManager();
    }
});

// Initialize Analysis Tab
function initializeAnalysisTab() {
    // Set current month as default
    const currentMonth = new Date().getMonth() + 1; // JavaScript months are 0-based
    document.getElementById('analysis-month').value = currentMonth;

    // Populate units dropdown
    populateAnalysisUnits();

    // Set up event listener for the Run Analysis button
    document.getElementById('run-analysis-btn').addEventListener('click', runExpenseAnalysis);
}

// Populate units dropdown for analysis tab
function populateAnalysisUnits() {
    fetch('/api/get_units')
        .then(response => response.json())
        .then(units => {
            const unitSelect = document.getElementById('analysis-unit');

            // Clear existing options except "All Units"
            while (unitSelect.options.length > 1) {
                unitSelect.remove(1);
            }

            // Add units to dropdown
            units.forEach(unit => {
                const option = document.createElement('option');
                option.value = unit.id;
                option.textContent = unit.unit_number;
                unitSelect.appendChild(option);
            });
        })
        .catch(error => {
            console.error('Error loading units:', error);
        });
}

// Run the expense analysis
function runExpenseAnalysis() {
    const month = document.getElementById('analysis-month').value;
    const unitId = document.getElementById('analysis-unit').value;
    const year = document.getElementById('report-year').value; // Use the same year as the report tab

    // Show loading indicator
    document.getElementById('analysis-loading').style.display = 'flex';

    // In a real implementation, you would fetch the data from your API
    // For now, we'll simulate a delay and then show some placeholder content
    setTimeout(() => {
        // Hide loading
        document.getElementById('analysis-loading').style.display = 'none';

        // Display placeholder analysis
        const analysisResults = document.getElementById('analysis-results');
        const monthName = document.getElementById('analysis-month').options[document.getElementById('analysis-month').selectedIndex].text;
        const unitName = document.getElementById('analysis-unit').options[document.getElementById('analysis-unit').selectedIndex].text;

        analysisResults.innerHTML = `
            <h3>Expense Analysis for ${monthName} ${year}</h3>
            <h4>Unit: ${unitName}</h4>

            <div class="analysis-metrics" style="margin-top: 20px;">
                <div class="metric-card" style="background-color: #f8f9fa; padding: 15px; border-radius: 8px; margin-bottom: 15px;">
                    <h5 style="margin-top: 0;">Revenue vs. Expenses</h5>
                    <div class="metric-content" style="display: flex; justify-content: space-between;">
                        <div style="text-align: center; padding: 10px;">
                            <div style="font-size: 1.5rem; font-weight: bold; color: #28a745;">RM 3,500</div>
                            <div>Total Revenue</div>
                        </div>
                        <div style="text-align: center; padding: 10px;">
                            <div style="font-size: 1.5rem; font-weight: bold; color: #dc3545;">RM 2,100</div>
                            <div>Total Expenses</div>
                        </div>
                        <div style="text-align: center; padding: 10px;">
                            <div style="font-size: 1.5rem; font-weight: bold; color: #17a2b8;">RM 1,400</div>
                            <div>Net Profit</div>
                        </div>
                    </div>
                </div>

                <div class="expense-breakdown" style="margin-top: 20px;">
                    <h5>Expense Breakdown</h5>
                    <div class="breakdown-chart" style="height: 30px; background-color: #e9ecef; border-radius: 4px; overflow: hidden; display: flex;">
                        <div style="width: 35%; height: 100%; background-color: #dc3545;" title="Rental: 35%"></div>
                        <div style="width: 20%; height: 100%; background-color: #fd7e14;" title="Utilities: 20%"></div>
                        <div style="width: 15%; height: 100%; background-color: #ffc107;" title="Maintenance: 15%"></div>
                        <div style="width: 30%; height: 100%; background-color: #6c757d;" title="Others: 30%"></div>
                    </div>
                    <div style="display: flex; margin-top: 10px; flex-wrap: wrap;">
                        <div style="margin-right: 15px; display: flex; align-items: center;">
                            <div style="width: 12px; height: 12px; background-color: #dc3545; margin-right: 5px;"></div>
                            <span>Rental (35%)</span>
                        </div>
                        <div style="margin-right: 15px; display: flex; align-items: center;">
                            <div style="width: 12px; height: 12px; background-color: #fd7e14; margin-right: 5px;"></div>
                            <span>Utilities (20%)</span>
                        </div>
                        <div style="margin-right: 15px; display: flex; align-items: center;">
                            <div style="width: 12px; height: 12px; background-color: #ffc107; margin-right: 5px;"></div>
                            <span>Maintenance (15%)</span>
                        </div>
                        <div style="margin-right: 15px; display: flex; align-items: center;">
                            <div style="width: 12px; height: 12px; background-color: #6c757d; margin-right: 5px;"></div>
                            <span>Others (30%)</span>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }, 1000);
}

// Add Analysis tab initialization to DOMContentLoaded
document.addEventListener('DOMContentLoaded', function() {
    // Existing code...

    // Initialize Analysis Tab
    initializeAnalysisTab();
});

// Initialize the Analysis tab
function initializeAnalysisTab() {
    // Populate the unit dropdown
    populateAnalysisUnits();

    // Set current month
    const now = new Date();
    const currentMonthYear = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
    const monthYearSelect = document.getElementById('analysis-month-year');
    if (monthYearSelect.querySelector(`option[value="${currentMonthYear}"]`)) {
        monthYearSelect.value = currentMonthYear;
    }

    // Set up event listeners
    document.getElementById('analysis-month-year').addEventListener('change', function() {
        const activeOption = document.querySelector('.analysis-option.active');
        if (activeOption && activeOption.getAttribute('data-analysis') === 'pl-statement') {
            updatePnLStatement();
        } else {
            updateAnalysis(); // Your existing function for the expenses breakdown
        }
    });
    document.getElementById('analysis-unit').addEventListener('change', updateAnalysis);
    document.getElementById('refresh-analysis-btn').addEventListener('click', updateAnalysis);

    // Initialize the pie chart
    initializeExpenseChart();

    // Load initial data
    updateAnalysis();
}

// Populate units dropdown for analysis
function populateAnalysisUnits() {
    fetch('/api/get_units')
        .then(response => response.json())
        .then(units => {
            const unitSelect = document.getElementById('analysis-unit');

            // Clear existing options except "All Units"
            while (unitSelect.options.length > 1) {
                unitSelect.remove(1);
            }

            // Add units to dropdown
            units.forEach(unit => {
                const option = document.createElement('option');
                option.value = unit.id;
                option.textContent = unit.unit_number;
                unitSelect.appendChild(option);
            });
        })
        .catch(error => {
            console.error('Error loading units:', error);
        });
}

// Chart instance
let expensePieChart = null;

// Initialize the expense chart
function initializeExpenseChart() {
    const ctx = document.getElementById('expense-pie-chart').getContext('2d');

    expensePieChart = new Chart(ctx, {
        type: 'pie',
        data: {
            labels: [],
            datasets: [{
                data: [],
                backgroundColor: [
                    '#dc3545', // red
                    '#fd7e14', // orange
                    '#ffc107', // yellow
                    '#20c997', // teal
                    '#0dcaf0', // cyan
                    '#6610f2', // indigo
                    '#6f42c1', // purple
                    '#d63384', // pink
                    '#198754', // green
                    '#0d6efd'  // blue
                ],
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'right',
                    labels: {
                        boxWidth: 15,
                        padding: 15
                    }
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            const label = context.label || '';
                            const value = context.parsed || 0;
                            const total = context.dataset.data.reduce((a, b) => a + b, 0);
                            const percentage = Math.round((value / total) * 100);
                            return `${label}: RM ${value.toLocaleString()} (${percentage}%)`;
                        }
                    }
                }
            }
        }
    });
}

// Update the analysis based on selected month and unit
// Update the analysis based on selected month and unit
// Update the analysis based on selected month and unit
function updateAnalysis() {
    const selectedMonthYear = document.getElementById('analysis-month-year').value;
    const selectedUnit = document.getElementById('analysis-unit').value;

    // Parse year and month
    const [year, month] = selectedMonthYear.split('-').map(Number);

    // Calculate previous month
    let prevYear = year;
    let prevMonth = month - 1;

    if (prevMonth === 0) {
        prevMonth = 12;
        prevYear--;
    }

    // Show loading state
    document.querySelector('.analysis-content').classList.add('loading');

    // Fetch data for current month
    fetch(`/api/expenses?year=${year}&month=${month}`)
        .then(response => response.json())
        .then(currentData => {
            // Process the current month expense data
            const currentExpenseData = processExpenseData(currentData, selectedUnit);

            // Now fetch previous month's data
            fetch(`/api/expenses?year=${prevYear}&month=${prevMonth}`)
                .then(response => response.json())
                .then(prevData => {
                    // Process the previous month expense data
                    const prevExpenseData = processExpenseData(prevData, selectedUnit);

                    // Calculate percentage change
                    const percentChange = calculatePercentChange(
                        prevExpenseData.total,
                        currentExpenseData.total
                    );

                    // Update the UI with the data
                    updateExpenseDisplay(currentExpenseData, percentChange);

                    // Hide loading state
                    document.querySelector('.analysis-content').classList.remove('loading');

                    // Fetch and display top units if needed
                    if (selectedUnit === 'all') {
                        fetchTopExpenseUnits(year, month);
                    } else {
                        document.querySelector('.top-units-section').style.display = 'none';
                    }
                })
                .catch(error => {
                    console.error('Error fetching previous month data:', error);
                    // Still update the UI with current month data
                    updateExpenseDisplay(currentExpenseData);
                    document.querySelector('.analysis-content').classList.remove('loading');

                    // Fetch and display top units if needed
                    if (selectedUnit === 'all') {
                        fetchTopExpenseUnits(year, month);
                    } else {
                        document.querySelector('.top-units-section').style.display = 'none';
                    }
                });
        })
        .catch(error => {
            console.error('Error fetching current month data:', error);
            document.querySelector('.analysis-content').classList.remove('loading');
            document.querySelector('.analysis-content').innerHTML =
                '<p class="error-message">Failed to load expense data. Please try again.</p>';
        });
}

// Helper function to calculate percentage change
function calculatePercentChange(oldValue, newValue) {
    if (oldValue === 0) {
        return newValue > 0 ? 100 : 0; // If old value was 0, and new value > 0, then it's a 100% increase
    }

    return ((newValue - oldValue) / oldValue) * 100;
}


// Process real expense data
function processExpenseData(apiData, unitId) {
    const units = apiData.units || [];
    const expenses = apiData.expenses || {};

    // Filter to just the selected unit if specified
    let filteredUnits = units;
    if (unitId !== 'all') {
        filteredUnits = units.filter(unit => unit.id == unitId);
    }

    // Initialize categories with all expense types
    const categories = [
        { name: 'Rental', amount: 0 },
        { name: 'Electricity', amount: 0 },
        { name: 'Water', amount: 0 },
        { name: 'Sewage', amount: 0 },
        { name: 'Internet', amount: 0 },
        { name: 'Cleaner', amount: 0 },
        { name: 'Laundry', amount: 0 },
        { name: 'Supplies', amount: 0 },
        { name: 'Repair', amount: 0 },
        { name: 'Replace', amount: 0 },
        { name: 'Other', amount: 0 }
    ];

    // Calculate totals by expense category
    let total = 0;

    filteredUnits.forEach(unit => {
        const unitExpenses = expenses[unit.id] || {};

        // Add each expense type to the appropriate category
        if (unitExpenses.rental) categories.find(c => c.name === 'Rental').amount += parseFloat(unitExpenses.rental) || 0;
        if (unitExpenses.electricity) categories.find(c => c.name === 'Electricity').amount += parseFloat(unitExpenses.electricity) || 0;
        if (unitExpenses.water) categories.find(c => c.name === 'Water').amount += parseFloat(unitExpenses.water) || 0;
        if (unitExpenses.sewage) categories.find(c => c.name === 'Sewage').amount += parseFloat(unitExpenses.sewage) || 0;
        if (unitExpenses.internet) categories.find(c => c.name === 'Internet').amount += parseFloat(unitExpenses.internet) || 0;
        if (unitExpenses.cleaner) categories.find(c => c.name === 'Cleaner').amount += parseFloat(unitExpenses.cleaner) || 0;
        if (unitExpenses.laundry) categories.find(c => c.name === 'Laundry').amount += parseFloat(unitExpenses.laundry) || 0;
        if (unitExpenses.supplies) categories.find(c => c.name === 'Supplies').amount += parseFloat(unitExpenses.supplies) || 0;
        if (unitExpenses.repair) categories.find(c => c.name === 'Repair').amount += parseFloat(unitExpenses.repair) || 0;
        if (unitExpenses.replace) categories.find(c => c.name === 'Replace').amount += parseFloat(unitExpenses.replace) || 0;
        if (unitExpenses.other) categories.find(c => c.name === 'Other').amount += parseFloat(unitExpenses.other) || 0;
    });

    // Remove categories with zero amount
    const nonZeroCategories = categories.filter(cat => cat.amount > 0);

    // Calculate total
    total = nonZeroCategories.reduce((sum, category) => sum + category.amount, 0);

    // Calculate percentages
    nonZeroCategories.forEach(category => {
        category.percentage = Math.round((category.amount / total) * 100);
    });

    // Sort by amount (highest to lowest)
    nonZeroCategories.sort((a, b) => b.amount - a.amount);

    // Find top expense
    const topExpense = nonZeroCategories.length > 0 ? nonZeroCategories[0] : { name: 'None', percentage: 0 };

    // Calculate average per unit
    const unitCount = filteredUnits.length;
    const avgPerUnit = unitCount > 0 ? Math.round(total / unitCount) : 0;

    return {
        total: total,
        categories: nonZeroCategories,
        topExpense: topExpense,
        avgPerUnit: avgPerUnit,
        unitCount: unitCount
    };
}

// Get sample expense data (in a real app, you would fetch this from your backend)
function getSampleExpenseData(year, month, unitId) {
    // Sample expense categories with amounts
    const categories = [
        { name: 'Electricity', amount: 24000 },
        { name: 'Water', amount: 2400 },
        { name: 'Sewage', amount: 480 },
        { name: 'Internet', amount: 2400 },
        { name: 'Cleaner', amount: 29400 }
    ];

    // Calculate total
    const total = categories.reduce((sum, category) => sum + category.amount, 0);

    // Calculate percentages
    const data = categories.map(category => {
        return {
            ...category,
            percentage: Math.round((category.amount / total) * 100)
        };
    });

    // Sort by amount (highest to lowest)
    data.sort((a, b) => b.amount - a.amount);

    // Find top expense
    const topExpense = data[0];

    // Calculate average per unit (sample uses 10 units for "all")
    const unitCount = unitId === 'all' ? 10 : 1;
    const avgPerUnit = Math.round(total / unitCount);

    return {
        total,
        categories: data,
        topExpense,
        avgPerUnit,
        unitCount
    };
}

// Update the UI with expense data
// Update the UI with expense data
function updateExpenseDisplay(data, percentChange = null) {
    // Update the metrics cards
    document.getElementById('total-expenses-value').textContent = `RM ${data.total.toLocaleString()}`;

    // Update the percentage change if available
    const expensesChangeElement = document.getElementById('expenses-change');
    if (percentChange !== null) {
        const formattedChange = percentChange.toFixed(1);
        const isPositive = percentChange > 0;

        expensesChangeElement.innerHTML = `
            <span style="color: ${isPositive ? '#dc3545' : '#28a745'}">
                ${isPositive ? '+' : ''}${formattedChange}% vs previous month
            </span>
        `;
    } else {
        expensesChangeElement.innerHTML = '';
    }

    document.getElementById('top-expense-name').textContent = data.topExpense.name;
    document.getElementById('top-expense-amount').textContent = `RM${data.topExpense.amount.toLocaleString()} (${data.topExpense.percentage}%)`;
    document.getElementById('avg-expense-value').textContent = `RM ${data.avgPerUnit.toLocaleString()}`;
    document.getElementById('units-count').textContent = `${data.unitCount} units`;

    // Update the pie chart
    updateExpenseChart(data.categories);

    // Update the summary table
    updateExpenseSummary(data.categories, data.total);
}


// Update the expense pie chart
function updateExpenseChart(categories) {
    // Update chart data
    expensePieChart.data.labels = categories.map(c => c.name);
    expensePieChart.data.datasets[0].data = categories.map(c => c.amount);
    expensePieChart.update();
}

// Update the expense summary table
function updateExpenseSummary(categories, total) {
    const tbody = document.getElementById('expense-summary-tbody');
    tbody.innerHTML = '';

    // Add a row for each category
    categories.forEach(category => {
        const row = document.createElement('tr');

        // Create cells for category, amount, and percentage
        const categoryCell = document.createElement('td');
        categoryCell.textContent = category.name;

        const amountCell = document.createElement('td');
        amountCell.textContent = category.amount.toLocaleString();

        const percentageCell = document.createElement('td');
        percentageCell.textContent = `${category.percentage}%`;

        // Add cells to row
        row.appendChild(categoryCell);
        row.appendChild(amountCell);
        row.appendChild(percentageCell);

        // Add row to table
        tbody.appendChild(row);
    });

    // Update total in footer
    document.getElementById('summary-total-amount').textContent = total.toLocaleString();
}

// Add Analysis tab initialization to DOMContentLoaded
document.addEventListener('DOMContentLoaded', function() {
    // Existing code...

    // Initialize Analysis Tab
    initializeAnalysisTab();
});

// Function to fetch top expense units
function fetchTopExpenseUnits(year, month) {
    // Show the top units section
    document.querySelector('.top-units-section').style.display = 'block';

    fetch(`/api/expenses?year=${year}&month=${month}`)
        .then(response => response.json())
        .then(data => {
            const topUnits = calculateTopExpenseUnits(data);
            renderTopUnitsChart(topUnits);
        })
        .catch(error => {
            console.error('Error fetching top units data:', error);
            document.querySelector('.top-units-chart-container').innerHTML =
                '<p class="error-message">Failed to load top units data. Please try again.</p>';
        });
}

// Function to calculate top expense units
function calculateTopExpenseUnits(data) {
    const units = data.units || [];
    const expenses = data.expenses || {};

    // Calculate total expenses for each unit
    const unitExpenses = units.map(unit => {
        const unitData = expenses[unit.id] || {};

        // Sum all expense categories for this unit
        const totalExpense =
            parseFloat(unitData.rental || 0) +
            parseFloat(unitData.electricity || 0) +
            parseFloat(unitData.water || 0) +
            parseFloat(unitData.sewage || 0) +
            parseFloat(unitData.internet || 0) +
            parseFloat(unitData.cleaner || 0) +
            parseFloat(unitData.laundry || 0) +
            parseFloat(unitData.supplies || 0) +
            parseFloat(unitData.repair || 0) +
            parseFloat(unitData.replace || 0) +
            parseFloat(unitData.other || 0);

        return {
            id: unit.id,
            unit_number: unit.unit_number,
            total_expense: totalExpense
        };
    });

    // Filter out units with zero expenses
    const nonZeroUnits = unitExpenses.filter(unit => unit.total_expense > 0);

    // Sort by expense (highest to lowest)
    nonZeroUnits.sort((a, b) => b.total_expense - a.total_expense);

    // Get top 10 (or fewer if less than 10 exist)
    return nonZeroUnits.slice(0, 10);
}


// Function to render the top units chart
function renderTopUnitsChart(topUnits) {
    // Check if chart already exists and destroy it
    if (window.topUnitsChart instanceof Chart) {
        window.topUnitsChart.destroy();
    }

    const ctx = document.getElementById('top-units-chart').getContext('2d');

    // Prepare data for the chart
    const labels = topUnits.map(unit => unit.unit_number);
    const data = topUnits.map(unit => unit.total_expense);

    // Create gradient fill for bars
    const gradient = ctx.createLinearGradient(0, 0, 0, 400);
    gradient.addColorStop(0, 'rgba(238, 77, 45, 0.8)');
    gradient.addColorStop(1, 'rgba(238, 77, 45, 0.2)');

    // Create the chart
    window.topUnitsChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Total Expenses (RM)',
                data: data,
                backgroundColor: gradient,
                borderColor: 'rgba(238, 77, 45, 1)',
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return 'RM ' + context.parsed.y.toFixed(2);
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        callback: function(value) {
                            return 'RM ' + value;
                        }
                    }
                }
            }
        }
    });
}

// Add this in the existing script section or create a new script tag
document.addEventListener('DOMContentLoaded', function() {
    // Set up the analysis tab switching
    const analysisOptions = document.querySelectorAll('.analysis-option');

    analysisOptions.forEach(option => {
        option.addEventListener('click', function() {
            // Remove active class from all options
            analysisOptions.forEach(opt => opt.classList.remove('active'));

            // Add active class to clicked option
            this.classList.add('active');

            // Get the analysis type
            const analysisType = this.getAttribute('data-analysis');

            // Hide all analysis content
            document.querySelector('.analysis-content').style.display = 'none';
            document.querySelector('.pl-statement-content').style.display = 'none';

            // Show the selected analysis content
            if (analysisType === 'expenses-breakdown') {
                document.querySelector('.analysis-content').style.display = 'block';
            } else if (analysisType === 'pl-statement') {
                document.querySelector('.pl-statement-content').style.display = 'block';
                updatePnLStatement(); // Call this to load the real data

                // Here you could add code to load/refresh the P&L data if needed
                // updatePnLStatement();
            }
        });
    });
});


// This script fixes the unit selection in the P&L Statement tab

// 1. Fix the updatePnLStatement function to properly handle unit filtering
function updatePnLStatement() {
    // Get the current month and year from the filter
    const selectedMonthYear = document.getElementById('analysis-month-year').value;
    const [year, month] = selectedMonthYear.split('-').map(Number);

    // Get selected unit
    const selectedUnit = document.getElementById('analysis-unit').value;
    console.log("Updating P&L statement for unit:", selectedUnit);

    // Get previous month for comparison
    let prevYear = year;
    let prevMonth = month - 1;
    if (prevMonth === 0) {
        prevMonth = 12;
        prevYear--;
    }

    // Get previous month name for display
    const monthNames = ["January", "February", "March", "April", "May", "June",
                        "July", "August", "September", "October", "November", "December"];
    const prevMonthName = monthNames[prevMonth-1]; // Adjust index since array is 0-based

    // Show loading state
    document.querySelector('.pl-statement-content').classList.add('loading');

    // Update the title with unit information
    if (selectedUnit !== 'all') {
        const unitText = document.getElementById('analysis-unit').options[
            document.getElementById('analysis-unit').selectedIndex
        ].text;
        document.getElementById('pl-statement-subtitle').textContent =
            `${monthNames[month-1]} ${year} | Unit: ${unitText}`;
    } else {
        document.getElementById('pl-statement-subtitle').textContent =
            `${monthNames[month-1]} ${year} | All Units`;
    }

    // Fetch data for current month
    fetch(`/api/expenses?year=${year}&month=${month}`)
        .then(response => response.json())
        .then(currentData => {
            // Get all units
            const units = currentData.units || [];
            const expenses = currentData.expenses || {};

            // Filter units if a specific unit is selected
            const filteredUnits = selectedUnit === 'all' ?
                units :
                units.filter(unit => unit.id == selectedUnit);

            console.log(`Found ${filteredUnits.length} units after filtering`);

            // Calculate totals
            let totalSales = 0;
            let totalRental = 0;
            let totalElectricity = 0;
            let totalWater = 0;
            let totalSewage = 0;
            let totalInternet = 0;
            let totalCleaner = 0;
            let totalLaundry = 0;
            let totalSupplies = 0;
            let totalRepair = 0;
            let totalReplace = 0;
            let totalOther = 0;

            // Process each unit's data
            filteredUnits.forEach(unit => {
                const unitId = unit.id;
                const unitExpenses = expenses[unitId] || {};

                // Sum up sales and expenses
                totalSales += parseFloat(unitExpenses.sales || 0);
                totalRental += parseFloat(unitExpenses.rental || 0);
                totalElectricity += parseFloat(unitExpenses.electricity || 0);
                totalWater += parseFloat(unitExpenses.water || 0);
                totalSewage += parseFloat(unitExpenses.sewage || 0);
                totalInternet += parseFloat(unitExpenses.internet || 0);
                totalCleaner += parseFloat(unitExpenses.cleaner || 0);
                totalLaundry += parseFloat(unitExpenses.laundry || 0);
                totalSupplies += parseFloat(unitExpenses.supplies || 0);
                totalRepair += parseFloat(unitExpenses.repair || 0);
                totalReplace += parseFloat(unitExpenses.replace || 0);
                totalOther += parseFloat(unitExpenses.other || 0);
            });

            // Calculate totals
            const totalRevenue = totalSales;
            const totalExpenses = totalRental + totalElectricity + totalWater + totalSewage +
                                 totalInternet + totalCleaner + totalLaundry + totalSupplies +
                                 totalRepair + totalReplace + totalOther;
            const netIncome = totalRevenue - totalExpenses;

            // Now fetch previous month data for comparison
            fetch(`/api/expenses?year=${prevYear}&month=${prevMonth}`)
                .then(response => response.json())
                .then(prevData => {
                    // Calculate previous month totals
                    let prevTotalSales = 0;
                    let prevTotalExpenses = 0;

                    const prevUnits = prevData.units || [];
                    const prevExpensesData = prevData.expenses || {};

                    // Filter previous month units if a specific unit is selected
                    const filteredPrevUnits = selectedUnit === 'all' ?
                        prevUnits :
                        prevUnits.filter(unit => unit.id == selectedUnit);

                    // Process each unit's data for previous month
                    filteredPrevUnits.forEach(unit => {
                        const unitId = unit.id;
                        const unitExpenses = prevExpensesData[unitId] || {};

                        // Sum up sales
                        prevTotalSales += parseFloat(unitExpenses.sales || 0);

                        // Sum up all expenses
                        prevTotalExpenses += parseFloat(unitExpenses.rental || 0);
                        prevTotalExpenses += parseFloat(unitExpenses.electricity || 0);
                        prevTotalExpenses += parseFloat(unitExpenses.water || 0);
                        prevTotalExpenses += parseFloat(unitExpenses.sewage || 0);
                        prevTotalExpenses += parseFloat(unitExpenses.internet || 0);
                        prevTotalExpenses += parseFloat(unitExpenses.cleaner || 0);
                        prevTotalExpenses += parseFloat(unitExpenses.laundry || 0);
                        prevTotalExpenses += parseFloat(unitExpenses.supplies || 0);
                        prevTotalExpenses += parseFloat(unitExpenses.repair || 0);
                        prevTotalExpenses += parseFloat(unitExpenses.replace || 0);
                        prevTotalExpenses += parseFloat(unitExpenses.other || 0);
                    });

                    const prevNetIncome = prevTotalSales - prevTotalExpenses;

                    // Calculate percentage changes
                    const revenueChange = prevTotalSales === 0 ? 0 : ((totalRevenue - prevTotalSales) / prevTotalSales) * 100;
                    const expensesChange = prevTotalExpenses === 0 ? 0 : ((totalExpenses - prevTotalExpenses) / prevTotalExpenses) * 100;
                    const incomeChange = prevNetIncome === 0 ? 0 : ((netIncome - prevNetIncome) / prevNetIncome) * 100;

                    // Update summary cards
                    document.getElementById('pl-total-revenue').textContent = formatNumber(totalRevenue);
                    document.getElementById('pl-revenue-change').textContent = revenueChange.toFixed(1);
                    document.getElementById('pl-revenue-prev-month').textContent = prevMonthName;

                    document.getElementById('pl-total-expenses').textContent = formatNumber(totalExpenses);
                    document.getElementById('pl-expenses-change').textContent = (expensesChange >= 0 ? '+' + expensesChange.toFixed(1) : expensesChange.toFixed(1));

                    document.getElementById('pl-expenses-prev-month').textContent = prevMonthName;

                    document.getElementById('pl-net-income').textContent = formatNumber(netIncome);
                    document.getElementById('pl-income-change').textContent = (incomeChange >= 0 ? '+' + incomeChange.toFixed(1) : incomeChange.toFixed(1));

                    document.getElementById('pl-income-prev-month').textContent = prevMonthName;

                    // Update table content
                    updatePLTable(
                        totalSales, totalRental, totalElectricity, totalWater, totalSewage,
                        totalInternet, totalCleaner, totalLaundry, totalSupplies,
                        totalRepair, totalReplace, totalOther,
                        totalRevenue, totalExpenses
                    );

                    // Hide loading state
                    document.querySelector('.pl-statement-content').classList.remove('loading');
                })
                .catch(error => {
                    console.error('Error fetching previous month data:', error);
                    // Still update with current month data
                    updatePLTableWithoutComparison(
                        totalSales, totalRental, totalElectricity, totalWater, totalSewage,
                        totalInternet, totalCleaner, totalLaundry, totalSupplies,
                        totalRepair, totalReplace, totalOther,
                        totalRevenue, totalExpenses
                    );
                    document.querySelector('.pl-statement-content').classList.remove('loading');
                });
        })
        .catch(error => {
            console.error('Error fetching current month data:', error);
            document.querySelector('.pl-statement-content').classList.remove('loading');
            document.querySelector('.pl-statement-content').innerHTML =
                '<p class="error-message">Failed to load P&L data. Please try again.</p>';
        });
}

// 2. Make sure the event listeners properly handle P&L updates when unit changes
document.addEventListener('DOMContentLoaded', function() {
    // Set up the analysis tab switching and make sure the event listener works for P&L tab
    const analysisOptions = document.querySelectorAll('.analysis-option');

    analysisOptions.forEach(option => {
        option.addEventListener('click', function() {
            // Remove active class from all options
            analysisOptions.forEach(opt => opt.classList.remove('active'));

            // Add active class to clicked option
            this.classList.add('active');

            // Get the analysis type
            const analysisType = this.getAttribute('data-analysis');

            // Hide all analysis content
            document.querySelector('.analysis-content').style.display = 'none';
            document.querySelector('.pl-statement-content').style.display = 'none';

            // Show the selected analysis content
            if (analysisType === 'expenses-breakdown') {
                document.querySelector('.analysis-content').style.display = 'block';
                // Refresh expenses breakdown analysis
                updateAnalysis();
            } else if (analysisType === 'pl-statement') {
                document.querySelector('.pl-statement-content').style.display = 'block';
                // Update P&L statement with current selections
                updatePnLStatement();
            }
        });
    });

    // Ensure the unit selection change handler updates the P&L statement when appropriate
    document.getElementById('analysis-unit').addEventListener('change', function() {
        // Check which analysis is currently active
        const activeAnalysis = document.querySelector('.analysis-option.active')?.getAttribute('data-analysis');

        if (activeAnalysis === 'pl-statement') {
            // Update the P&L statement if that's the active view
            updatePnLStatement();
        } else {
            // Otherwise update the regular analysis
            updateAnalysis();
        }
    });
});

// Helper function to format numbers with commas
function formatNumber(num) {
    return num.toLocaleString('en-US', {maximumFractionDigits: 0});
}

// Function to update the P&L table with real data
function updatePLTable(totalSales, totalRental, totalElectricity, totalWater, totalSewage,
                     totalInternet, totalCleaner, totalLaundry, totalSupplies,
                     totalRepair, totalReplace, totalOther,
                     totalRevenue, totalExpenses) {

    const tableBody = document.getElementById('pl-table-body');
    if (!tableBody) return;

    // Clear existing rows
    tableBody.innerHTML = '';

    // Create income section
    const incomeRow = document.createElement('tr');
    incomeRow.style.backgroundColor = '#f5f7f9';
    incomeRow.innerHTML = `
        <td style="padding: 12px 15px; font-weight: bold;">Income</td>
        <td></td>
        <td></td>
        <td></td>
    `;
    tableBody.appendChild(incomeRow);

    // Add sales row
    const salesRow = document.createElement('tr');
    const salesPercentage = (totalRevenue > 0) ? ((totalSales / totalRevenue) * 100).toFixed(0) : 0;
    salesRow.innerHTML = `
        <td style="padding: 12px 15px; border-bottom: 1px solid #f0f0f0;">Sales</td>
        <td style="padding: 12px 15px; text-align: right; border-bottom: 1px solid #f0f0f0;">${formatNumber(totalSales)}</td>
        <td style="padding: 12px 15px; text-align: right; border-bottom: 1px solid #f0f0f0;">${salesPercentage}%</td>
        <td style="padding: 12px 15px; text-align: right; border-bottom: 1px solid #f0f0f0; color: #4CAF50;">${parseFloat(document.getElementById('pl-revenue-change').textContent).toFixed(1)}%</td>
    `;
    tableBody.appendChild(salesRow);

    // Create expenses section
    const expensesRow = document.createElement('tr');
    expensesRow.style.backgroundColor = '#f5f7f9';
    expensesRow.innerHTML = `
        <td style="padding: 12px 15px; font-weight: bold;">Expenses</td>
        <td></td>
        <td></td>
        <td></td>
    `;
    tableBody.appendChild(expensesRow);

    // Add expense rows with previous month comparison
    // Fetch the previous month values from the summary cards
    const expensesChangePercent = parseFloat(document.getElementById('pl-expenses-change').textContent);

    // This is a simplified approach since we don't have individual expense category changes
    // In a real implementation, you'd calculate these individually
    addExpenseRowWithComparison(tableBody, 'Rental', totalRental, totalExpenses, expensesChangePercent);
    addExpenseRowWithComparison(tableBody, 'Electricity', totalElectricity, totalExpenses, expensesChangePercent);
    addExpenseRowWithComparison(tableBody, 'Water', totalWater, totalExpenses, expensesChangePercent);
    addExpenseRowWithComparison(tableBody, 'Sewage', totalSewage, totalExpenses, expensesChangePercent);
    addExpenseRowWithComparison(tableBody, 'Internet', totalInternet, totalExpenses, expensesChangePercent);
    addExpenseRowWithComparison(tableBody, 'Cleaner', totalCleaner, totalExpenses, expensesChangePercent);
    addExpenseRowWithComparison(tableBody, 'Laundry', totalLaundry, totalExpenses, expensesChangePercent);
    addExpenseRowWithComparison(tableBody, 'Supplies', totalSupplies, totalExpenses, expensesChangePercent);
    addExpenseRowWithComparison(tableBody, 'Repair', totalRepair, totalExpenses, expensesChangePercent);
    addExpenseRowWithComparison(tableBody, 'Replace', totalReplace, totalExpenses, expensesChangePercent);
    addExpenseRowWithComparison(tableBody, 'Other', totalOther, totalExpenses, expensesChangePercent);

    // Add Total row
    const netIncomeChangePercent = parseFloat(document.getElementById('pl-income-change').textContent);
    const netIncome = totalRevenue - totalExpenses;
    const netIncomePercentage = (totalRevenue > 0) ? ((netIncome / totalRevenue) * 100).toFixed(0) : 0;

    const totalRow = document.createElement('tr');
    totalRow.style.backgroundColor = '#e9ecef';
    totalRow.style.fontWeight = 'bold';
    totalRow.innerHTML = `
        <td style="padding: 12px 15px;">Net Income</td>
        <td style="padding: 12px 15px; text-align: right;">${formatNumber(netIncome)}</td>
        <td style="padding: 12px 15px; text-align: right;">${netIncomePercentage}%</td>
        <td style="padding: 12px 15px; text-align: right; color: ${netIncomeChangePercent >= 0 ? '#4CAF50' : '#FF5722'};">${netIncomeChangePercent.toFixed(1)}%</td>
    `;
    tableBody.appendChild(totalRow);
}

// Helper function to add expense rows with comparison data
function addExpenseRowWithComparison(tableBody, label, amount, totalExpenses, changePercent) {
    if (amount <= 0) return; // Skip zero amounts

    const row = document.createElement('tr');
    const percentage = (totalExpenses > 0) ? ((amount / totalExpenses) * 100).toFixed(0) : 0;

    row.innerHTML = `
        <td style="padding: 12px 15px; border-bottom: 1px solid #f0f0f0;">${label}</td>
        <td style="padding: 12px 15px; text-align: right; border-bottom: 1px solid #f0f0f0;">${formatNumber(amount)}</td>
        <td style="padding: 12px 15px; text-align: right; border-bottom: 1px solid #f0f0f0;">${percentage}%</td>
        <td style="padding: 12px 15px; text-align: right; border-bottom: 1px solid #f0f0f0; color: ${changePercent >= 0 ? '#FF5722' : '#4CAF50'};">${changePercent.toFixed(1)}%</td>
    `;

    tableBody.appendChild(row);
}
// Helper function to add expense rows
function addExpenseRow(tableBody, label, amount, totalExpenses) {
    if (amount <= 0) return; // Skip zero amounts

    const row = document.createElement('tr');
    const percentage = (totalExpenses > 0) ? ((amount / totalExpenses) * 100).toFixed(0) : 0;

    row.innerHTML = `
        <td style="padding: 12px 15px; border-bottom: 1px solid #f0f0f0;">${label}</td>
        <td style="padding: 12px 15px; text-align: right; border-bottom: 1px solid #f0f0f0;">${formatNumber(amount)}</td>
        <td style="padding: 12px 15px; text-align: right; border-bottom: 1px solid #f0f0f0;">${percentage}%</td>
        <td style="padding: 12px 15px; text-align: right; border-bottom: 1px solid #f0f0f0; color: #FF5722;"></td>
    `;

    tableBody.appendChild(row);
}


// Initialize YoY comparison data and chart
function initializeYoYComparison() {
    // Set up month-year dropdown event listener
    document.getElementById('analysis-month-year').addEventListener('change', function() {
        const activeOption = document.querySelector('.analysis-option.active');
        if (activeOption && activeOption.getAttribute('data-analysis') === 'yoy-comparison') {
            updateYoYComparison();
        }
    });

    // Set up unit dropdown event listener
    document.getElementById('analysis-unit').addEventListener('change', function() {
        const activeOption = document.querySelector('.analysis-option.active');
        if (activeOption && activeOption.getAttribute('data-analysis') === 'yoy-comparison') {
            updateYoYComparison();
        }
    });

    // Initialize the chart
    const ctx = document.getElementById('yoy-trend-chart').getContext('2d');
    window.yoyTrendChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'],
            datasets: []
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        callback: function(value) {
                            return 'RM' + value.toLocaleString();
                        }
                    }
                }
            },
            plugins: {
                legend: {
                    position: 'top'
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            let label = context.dataset.label || '';
                            if (label) {
                                label += ': ';
                            }
                            if (context.parsed.y !== null) {
                                label += 'RM' + context.parsed.y.toLocaleString();
                            }
                            return label;
                        }
                    }
                }
            }
        }
    });
}

// Update YoY comparison data and visualization
function updateYoYComparison() {
    const selectedMonthYear = document.getElementById('analysis-month-year').value;
    const selectedUnit = document.getElementById('analysis-unit').value;

    // Parse current year and month
    const [currentYear, currentMonth] = selectedMonthYear.split('-').map(Number);

    // Calculate previous year (same month)
    const previousYear = currentYear - 1;

    // Update title and subtitle
    const monthNames = ["January", "February", "March", "April", "May", "June",
                      "July", "August", "September", "October", "November", "December"];
    const monthName = monthNames[currentMonth - 1];

    // Update subtitle based on selected unit
    let unitText = "All Properties";
    if (selectedUnit !== 'all') {
        const unitSelect = document.getElementById('analysis-unit');
        unitText = unitSelect.options[unitSelect.selectedIndex].text;
    }

    document.getElementById('yoy-comparison-subtitle').textContent =
        `${monthName} ${currentYear} vs ${monthName} ${previousYear} | ${unitText}`;

    // Show loading state
    document.querySelector('.yoy-comparison-content').classList.add('loading');

    // Fetch data for current year month
    fetchMonthlyDataForYear(currentYear, selectedUnit)
        .then(currentYearData => {
            // Fetch data for previous year
            fetchMonthlyDataForYear(previousYear, selectedUnit)
                .then(previousYearData => {
                    // Update the comparison cards
                    updateYoYComparisonCards(currentYearData, previousYearData, currentMonth);

                    // Update the trend chart
                    updateYoYTrendChart(currentYearData, previousYearData, currentYear, previousYear);

                    // Hide loading state
                    document.querySelector('.yoy-comparison-content').classList.remove('loading');
                })
                .catch(error => {
                    console.error("Error fetching previous year data:", error);
                    document.querySelector('.yoy-comparison-content').classList.remove('loading');
                });
        })
        .catch(error => {
            console.error("Error fetching current year data:", error);
            document.querySelector('.yoy-comparison-content').classList.remove('loading');
        });
}

// Fetch monthly data for a specific year
function fetchMonthlyDataForYear(year, unitId) {
    return new Promise((resolve, reject) => {
        fetch(`/api/expenses/yearly?year=${year}&building=all`)
            .then(response => response.json())
            .then(data => {
                // Process the data
                const processedData = {
                    revenue: {},
                    expenses: {},
                    profit: {}
                };

                // Filter units if specific unit is selected
                let unitsToProcess = data.units;
                if (unitId !== 'all') {
                    unitsToProcess = data.units.filter(unit => unit.id == unitId);
                }

                // Initialize data structures for each month
                for (let month = 1; month <= 12; month++) {
                    processedData.revenue[month] = 0;
                    processedData.expenses[month] = 0;
                    processedData.profit[month] = 0;
                }

                // Process each unit's data
                unitsToProcess.forEach(unit => {
                    const unitId = unit.id;
                    const unitExpenses = data.expenses[unitId] || {};

                    // For each month
                    for (let month = 1; month <= 12; month++) {
                        const monthData = unitExpenses[month] || {};

                        // Revenue (sales)
                        const revenue = parseFloat(monthData.sales || 0);
                        processedData.revenue[month] += revenue;

                        // Calculate total expenses for this unit/month
                        const expenses =
                            parseFloat(monthData.rental || 0) +
                            parseFloat(monthData.electricity || 0) +
                            parseFloat(monthData.water || 0) +
                            parseFloat(monthData.sewage || 0) +
                            parseFloat(monthData.internet || 0) +
                            parseFloat(monthData.cleaner || 0) +
                            parseFloat(monthData.laundry || 0) +
                            parseFloat(monthData.supplies || 0) +
                            parseFloat(monthData.repair || 0) +
                            parseFloat(monthData.replace || 0) +
                            parseFloat(monthData.other || 0);

                        processedData.expenses[month] += expenses;

                        // Calculate profit
                        processedData.profit[month] += (revenue - expenses);
                    }
                });

                resolve(processedData);
            })
            .catch(error => {
                console.error(`Error fetching data for year ${year}:`, error);
                reject(error);
            });
    });
}

// Update the YoY comparison cards with real data
function updateYoYComparisonCards(currentYearData, previousYearData, currentMonth) {
    // Get the current month's data
    const currentRevenue = currentYearData.revenue[currentMonth] || 0;
    const currentExpenses = currentYearData.expenses[currentMonth] || 0;
    const currentProfit = currentYearData.profit[currentMonth] || 0;

    // Get the previous year's same month data
    const previousRevenue = previousYearData.revenue[currentMonth] || 0;
    const previousExpenses = previousYearData.expenses[currentMonth] || 0;
    const previousProfit = previousYearData.profit[currentMonth] || 0;

    // Calculate percentage changes
    let revenueChange = 0;
    if (previousRevenue > 0) {
        revenueChange = ((currentRevenue - previousRevenue) / previousRevenue) * 100;
    }

    let expensesChange = 0;
    if (previousExpenses > 0) {
        expensesChange = ((currentExpenses - previousExpenses) / previousExpenses) * 100;
    }

    let profitChange = 0;
    if (previousProfit > 0) {
        profitChange = ((currentProfit - previousProfit) / previousProfit) * 100;
    }

    // Update the display with formatted numbers
    document.getElementById('yoy-current-revenue').textContent = Math.round(currentRevenue).toLocaleString();
    document.getElementById('yoy-previous-revenue').textContent = Math.round(previousRevenue).toLocaleString();
    document.getElementById('yoy-revenue-change').textContent = (revenueChange >= 0 ? '+' : '') + revenueChange.toFixed(1) + '%';

    document.getElementById('yoy-current-expenses').textContent = Math.round(currentExpenses).toLocaleString();
    document.getElementById('yoy-previous-expenses').textContent = Math.round(previousExpenses).toLocaleString();
    document.getElementById('yoy-expenses-change').textContent = (expensesChange >= 0 ? '+' : '') + expensesChange.toFixed(1) + '%';

    document.getElementById('yoy-current-profit').textContent = Math.round(currentProfit).toLocaleString();
    document.getElementById('yoy-previous-profit').textContent = Math.round(previousProfit).toLocaleString();
    document.getElementById('yoy-profit-change').textContent = (profitChange >= 0 ? '+' : '') + profitChange.toFixed(1) + '%';

    // Set appropriate colors
    document.getElementById('yoy-revenue-change').style.color = (revenueChange >= 0) ? '#4CAF50' : '#F44336';
    document.getElementById('yoy-expenses-change').style.color = (expensesChange >= 0) ? '#F44336' : '#4CAF50';
    document.getElementById('yoy-profit-change').style.color = (profitChange >= 0) ? '#3F51B5' : '#F44336';
}

// Update the YoY trend chart with real data
function updateYoYTrendChart(currentYearData, previousYearData, currentYear, previousYear) {
    // Prepare datasets for the chart
    const datasets = [
        {
            label: currentYear + ' Revenue',
            data: Array.from({length: 12}, (_, i) => Math.round(currentYearData.revenue[i+1] || 0)),
            borderColor: '#4CAF50',
            backgroundColor: 'rgba(76, 175, 80, 0.1)',
            borderWidth: 2,
            fill: false
        },
        {
            label: previousYear + ' Revenue',
            data: Array.from({length: 12}, (_, i) => Math.round(previousYearData.revenue[i+1] || 0)),
            borderColor: '#4CAF50',
            backgroundColor: 'rgba(76, 175, 80, 0.1)',
            borderWidth: 2,
            borderDash: [5, 5],
            fill: false
        },
        {
            label: currentYear + ' Expenses',
            data: Array.from({length: 12}, (_, i) => Math.round(currentYearData.expenses[i+1] || 0)),
            borderColor: '#F44336',
            backgroundColor: 'rgba(244, 67, 54, 0.1)',
            borderWidth: 2,
            fill: false
        },
        {
            label: previousYear + ' Expenses',
            data: Array.from({length: 12}, (_, i) => Math.round(previousYearData.expenses[i+1] || 0)),
            borderColor: '#F44336',
            backgroundColor: 'rgba(244, 67, 54, 0.1)',
            borderWidth: 2,
            borderDash: [5, 5],
            fill: false
        }
    ];

    // Update the chart
    window.yoyTrendChart.data.datasets = datasets;
    window.yoyTrendChart.update();
}

// Add initialization to main document ready function
document.addEventListener('DOMContentLoaded', function() {
    // Existing initialization code...

    // Initialize YoY comparison
    initializeYoYComparison();

    // Modify the event listener for analysis options to include YoY comparison
    const analysisOptions = document.querySelectorAll('.analysis-option');
    analysisOptions.forEach(option => {
        option.addEventListener('click', function() {
            // Remove active class from all options
            analysisOptions.forEach(opt => opt.classList.remove('active'));

            // Add active class to clicked option
            this.classList.add('active');

            // Get the analysis type
            const analysisType = this.getAttribute('data-analysis');

            // Hide all analysis content
            document.querySelector('.analysis-content').style.display = 'none';
            document.querySelector('.pl-statement-content').style.display = 'none';
            document.querySelector('.yoy-comparison-content').style.display = 'none';

            // Show the selected analysis content
            if (analysisType === 'expenses-breakdown') {
                document.querySelector('.analysis-content').style.display = 'block';
                updateAnalysis(); // Refresh the data
            } else if (analysisType === 'pl-statement') {
                document.querySelector('.pl-statement-content').style.display = 'block';
                updatePnLStatement(); // Refresh the data
            } else if (analysisType === 'yoy-comparison') {
                document.querySelector('.yoy-comparison-content').style.display = 'block';
                updateYoYComparison(); // Load the YoY comparison data
            }
        });
    });
});

// Function to update the ROI Analysis data
function updateROIAnalysis() {
    // Get the selected month and year
    const selectedMonthYear = document.getElementById('analysis-month-year').value;
    const selectedUnit = document.getElementById('analysis-unit').value;

    // Parse year and month
    const [year, month] = selectedMonthYear.split('-').map(Number);

    // Update the subtitle
    const monthNames = ["January", "February", "March", "April", "May", "June",
                       "July", "August", "September", "October", "November", "December"];

    let unitText = "All Units";
    if (selectedUnit !== 'all') {
        const unitSelect = document.getElementById('analysis-unit');
        unitText = unitSelect.options[unitSelect.selectedIndex].text;
    }

    document.getElementById('roi-analysis-subtitle').textContent = `${monthNames[month-1]} ${year} | ${unitText}`;

    // Show loading state
    document.querySelector('.roi-analysis-content').classList.add('loading');

    // Fetch the data
    fetch(`/api/expenses?year=${year}&month=${month}`)
        .then(response => response.json())
        .then(data => {
            // Process the data
            const units = data.units || [];
            const expenses = data.expenses || {};

            // Filter units based on selection
            const filteredUnits = selectedUnit === 'all' ?
                units :
                units.filter(unit => unit.id == selectedUnit);

            // Clear existing table rows
            const tableBody = document.getElementById('roi-analysis-tbody');
            tableBody.innerHTML = '';

            // Variables for totals
            let totalNetProfit = 0;
            let totalRental = 0;

            // Create a row for each unit
            filteredUnits.forEach(unit => {
                const unitId = unit.id;
                const unitExpense = expenses[unitId] || {};

                // Calculate net profit and get rental value
                const sales = parseFloat(unitExpense.sales || 0);
                const rental = parseFloat(unitExpense.rental || 0);
                const otherExpenses =
                    parseFloat(unitExpense.electricity || 0) +
                    parseFloat(unitExpense.water || 0) +
                    parseFloat(unitExpense.sewage || 0) +
                    parseFloat(unitExpense.internet || 0) +
                    parseFloat(unitExpense.cleaner || 0) +
                    parseFloat(unitExpense.laundry || 0) +
                    parseFloat(unitExpense.supplies || 0) +
                    parseFloat(unitExpense.repair || 0) +
                    parseFloat(unitExpense.replace || 0) +
                    parseFloat(unitExpense.other || 0);

                const netProfit = sales - rental - otherExpenses;

                // Calculate ROI
                let roi = 0;
                if (rental > 0) {
                    roi = (netProfit / rental) * 100;
                }

                // Determine performance category
                let performance = 'Poor';
                let performanceColor = '#dc3545';

                if (roi >= 50) {
                    performance = 'Excellent';
                    performanceColor = '#28a745';
                } else if (roi >= 20) {
                    performance = 'Good';
                    performanceColor = '#007bff';
                } else if (roi >= 5) {
                    performance = 'Average';
                    performanceColor = '#fd7e14';
                }

                // Create table row
                const row = document.createElement('tr');
                row.dataset.netProfit = netProfit;
                row.dataset.rental = rental;
                row.dataset.roi = roi.toFixed(1);
                row.dataset.performance = performance;
                row.innerHTML = `
                    <td style="padding: 12px 15px; text-align: left; border-bottom: 1px solid #f0f0f0;">${unit.unit_number}</td>
                    <td style="padding: 12px 15px; text-align: right; border-bottom: 1px solid #f0f0f0;">RM${netProfit.toLocaleString(undefined, {minimumFractionDigits: 0, maximumFractionDigits: 0})}</td>
                    <td style="padding: 12px 15px; text-align: right; border-bottom: 1px solid #f0f0f0;">RM${rental.toLocaleString(undefined, {minimumFractionDigits: 0, maximumFractionDigits: 0})}</td>
                    <td style="padding: 12px 15px; text-align: center; border-bottom: 1px solid #f0f0f0;">${roi.toFixed(1)}%</td>
                    <td style="padding: 12px 15px; text-align: center; border-bottom: 1px solid #f0f0f0;">
                        <span style="display: inline-block; padding: 4px 12px; background-color: ${performanceColor}; color: white; border-radius: 20px;">${performance}</span>
                    </td>
                `;
                tableBody.appendChild(row);

                // Update totals
                totalNetProfit += netProfit;
                totalRental += rental;
            });

            // Calculate total ROI
            let totalRoi = 0;
            if (totalRental > 0) {
                totalRoi = (totalNetProfit / totalRental) * 100;
            }

            // Determine total performance
            let totalPerformance = 'Poor';
            let totalPerformanceColor = '#dc3545';

            if (totalRoi >= 50) {
                totalPerformance = 'Excellent';
                totalPerformanceColor = '#28a745';
            } else if (totalRoi >= 20) {
                totalPerformance = 'Good';
                totalPerformanceColor = '#007bff';
            } else if (totalRoi >= 5) {
                totalPerformance = 'Average';
                totalPerformanceColor = '#fd7e14';
            }

            // Update footer
            document.getElementById('roi-total-profit').textContent = `RM${totalNetProfit.toLocaleString(undefined, {minimumFractionDigits: 0, maximumFractionDigits: 0})}`;
            document.getElementById('roi-total-rental').textContent = `RM${totalRental.toLocaleString(undefined, {minimumFractionDigits: 0, maximumFractionDigits: 0})}`;
            document.getElementById('roi-total-percentage').textContent = `${totalRoi.toFixed(1)}%`;
            document.getElementById('roi-total-performance').innerHTML = `
                <span style="display: inline-block; padding: 4px 12px; background-color: ${totalPerformanceColor}; color: white; border-radius: 20px;">
                    ${totalPerformance}
                </span>
            `;

            // Hide loading state
            document.querySelector('.roi-analysis-content').classList.remove('loading');
        })
        .catch(error => {
            console.error('Error fetching expense data for ROI analysis:', error);
            document.querySelector('.roi-analysis-content').classList.remove('loading');
            document.querySelector('.roi-analysis-content').innerHTML = `
                <p class="error-message">Failed to load ROI analysis data. Please try again.</p>
            `;
        });
}

// Modify the existing event listener for analysis options to include ROI Analysis
document.addEventListener('DOMContentLoaded', function() {
    const analysisOptions = document.querySelectorAll('.analysis-option');
    if (analysisOptions.length > 0) {
        analysisOptions.forEach(option => {
            option.addEventListener('click', function() {
                // Remove active class from all options
                analysisOptions.forEach(opt => opt.classList.remove('active'));

                // Add active class to clicked option
                this.classList.add('active');

                // Get the analysis type
                const analysisType = this.getAttribute('data-analysis');

                // Hide all analysis content
                document.querySelector('.analysis-content').style.display = 'none';
                document.querySelector('.pl-statement-content').style.display = 'none';
                document.querySelector('.yoy-comparison-content').style.display = 'none';
                document.querySelector('.roi-analysis-content').style.display = 'none';

                // Show the selected analysis content
                if (analysisType === 'expenses-breakdown') {
                    document.querySelector('.analysis-content').style.display = 'block';
                    updateAnalysis(); // Refresh the data
                } else if (analysisType === 'pl-statement') {
                    document.querySelector('.pl-statement-content').style.display = 'block';
                    updatePnLStatement(); // Refresh the data
                } else if (analysisType === 'yoy-comparison') {
                    document.querySelector('.yoy-comparison-content').style.display = 'block';
                    updateYoYComparison(); // Load the YoY comparison data
                } else if (analysisType === 'roi-analysis') {
                    document.querySelector('.roi-analysis-content').style.display = 'block';
                    updateROIAnalysis(); // Load the ROI analysis data
                }
            });
        });
    }

    // Add event listeners for month and unit selector to update ROI analysis
    document.getElementById('analysis-month-year')?.addEventListener('change', function() {
        const activeOption = document.querySelector('.analysis-option.active');
        if (activeOption && activeOption.getAttribute('data-analysis') === 'roi-analysis') {
            updateROIAnalysis();
        }
    });

    document.getElementById('analysis-unit')?.addEventListener('change', function() {
        const activeOption = document.querySelector('.analysis-option.active');
        if (activeOption && activeOption.getAttribute('data-analysis') === 'roi-analysis') {
            updateROIAnalysis();
        }
    });
});

// Variable to track current sort state
let roiSortConfig = {
    column: null,
    direction: 'asc'
};

// Function to sort the ROI table
function sortROITable(column) {
    const tableBody = document.getElementById('roi-analysis-tbody');
    const rows = Array.from(tableBody.querySelectorAll('tr'));

    // Reset all indicators
    const indicators = document.querySelectorAll('[id^="sort-"][id$="-indicator"]');
    indicators.forEach(indicator => {
        indicator.textContent = '';
    });

    // Update sort configuration
    if (roiSortConfig.column === column) {
        // Toggle direction if same column is clicked
        roiSortConfig.direction = roiSortConfig.direction === 'asc' ? 'desc' : 'asc';
    } else {
        // Set new column and default to ascending
        roiSortConfig.column = column;
        roiSortConfig.direction = 'asc';
    }

    // Set the indicator for the current sort column
    const indicator = document.getElementById(`sort-${column}-indicator`);
    indicator.textContent = roiSortConfig.direction === 'asc' ? ' ▲' : ' ▼';

    // Sort the rows
    rows.sort((a, b) => {
        let valueA, valueB;

        if (column === 'unit') {
            // First cell contains unit name (text)
            valueA = a.cells[0].textContent.trim();
            valueB = b.cells[0].textContent.trim();
            return roiSortConfig.direction === 'asc'
                ? valueA.localeCompare(valueB)
                : valueB.localeCompare(valueA);

        } else if (column === 'profit' || column === 'rental') {
            // Extract numeric value from "RM1,234" format
            const indexMap = { 'profit': 1, 'rental': 2 };
            const cellIndex = indexMap[column];

            valueA = parseFloat(a.cells[cellIndex].textContent.replace(/[^0-9.-]+/g, ''));
            valueB = parseFloat(b.cells[cellIndex].textContent.replace(/[^0-9.-]+/g, ''));

        } else if (column === 'roi') {
            // Extract percentage value
            valueA = parseFloat(a.cells[3].textContent);
            valueB = parseFloat(b.cells[3].textContent);

        } else if (column === 'performance') {
            // Map performance to numeric values for sorting
            const performanceMap = {
                'Excellent': 4,
                'Good': 3,
                'Average': 2,
                'Poor': 1
            };

            const textA = a.cells[4].querySelector('span').textContent.trim();
            const textB = b.cells[4].querySelector('span').textContent.trim();

            valueA = performanceMap[textA] || 0;
            valueB = performanceMap[textB] || 0;
        }

        // For numeric comparisons
        if (column !== 'unit') {
            if (isNaN(valueA)) valueA = 0;
            if (isNaN(valueB)) valueB = 0;

            return roiSortConfig.direction === 'asc'
                ? valueA - valueB
                : valueB - valueA;
        }
    });

    // Reappend rows in the new order
    rows.forEach(row => {
        tableBody.appendChild(row);
    });
}


// Income by Unit Analysis
function initializeIncomeByUnitAnalysis() {
    // Set up chart/table view toggle
    document.getElementById('income-chart-view').addEventListener('click', function() {
        this.classList.add('active');
        document.getElementById('income-table-view').classList.remove('active');
        document.getElementById('income-chart-container').style.display = 'block';
        document.getElementById('income-table-container').style.display = 'none';
    });

    document.getElementById('income-table-view').addEventListener('click', function() {
        this.classList.add('active');
        document.getElementById('income-chart-view').classList.remove('active');
        document.getElementById('income-chart-container').style.display = 'none';
        document.getElementById('income-table-container').style.display = 'block';
    });
}

// Function to update Income by Unit analysis
function updateIncomeByUnitAnalysis() {
    const selectedMonthYear = document.getElementById('analysis-month-year').value;
    const selectedUnit = document.getElementById('analysis-unit').value;

    // Parse year and month
    const [year, month] = selectedMonthYear.split('-').map(Number);

    // Update the subtitle
    const monthNames = ["January", "February", "March", "April", "May", "June",
                       "July", "August", "September", "October", "November", "December"];

    let unitText = "All Units";
    if (selectedUnit !== 'all') {
        const unitSelect = document.getElementById('analysis-unit');
        unitText = unitSelect.options[unitSelect.selectedIndex].text;
    }

    document.getElementById('income-by-unit-subtitle').textContent = `${monthNames[month-1]} ${year} | ${unitText}`;

    // Show loading state
    document.querySelector('.income-by-unit-content').classList.add('loading');

    // Fetch the data
    fetch(`/api/expenses?year=${year}&month=${month}`)
        .then(response => response.json())
        .then(data => {
            // Process the data
            const units = data.units || [];
            const expenses = data.expenses || {};

            // Filter units based on selection
            const filteredUnits = selectedUnit === 'all' ?
                units :
                units.filter(unit => unit.id == selectedUnit);

            // Calculate income data for each unit
            const unitData = filteredUnits.map(unit => {
                const unitExpense = expenses[unit.id] || {};

                // Calculate sales income
                const salesIncome = parseFloat(unitExpense.sales || 0);

                // Calculate total expenses
                const totalExpenses =
                    parseFloat(unitExpense.rental || 0) +
                    parseFloat(unitExpense.electricity || 0) +
                    parseFloat(unitExpense.water || 0) +
                    parseFloat(unitExpense.sewage || 0) +
                    parseFloat(unitExpense.internet || 0) +
                    parseFloat(unitExpense.cleaner || 0) +
                    parseFloat(unitExpense.laundry || 0) +
                    parseFloat(unitExpense.supplies || 0) +
                    parseFloat(unitExpense.repair || 0) +
                    parseFloat(unitExpense.replace || 0) +
                    parseFloat(unitExpense.other || 0);

                // Calculate net profit
                const netProfit = salesIncome - totalExpenses;

                // Calculate profit margin
                const profitMargin = salesIncome > 0 ? (netProfit / salesIncome) * 100 : 0;

                return {
                    unitNumber: unit.unit_number,
                    salesIncome: salesIncome,
                    netProfit: netProfit,
                    profitMargin: profitMargin
                };
            });

            // Store data globally for sorting
            currentIncomeData = unitData;

            // Update the chart
            updateIncomeChart(unitData);

            // Update the table with current sort
            updateIncomeTable(unitData, currentIncomeSort);

            // Setup sorting (only needs to be called once, but safe to call multiple times)
            setupIncomeSorting();

            // Hide loading state
            document.querySelector('.income-by-unit-content').classList.remove('loading');
        })
        .catch(error => {
            console.error('Error fetching expense data:', error);
            document.querySelector('.income-by-unit-content').classList.remove('loading');
            document.querySelector('.income-by-unit-content').innerHTML = `
                <p class="error-message">Failed to load income data. Please try again.</p>
            `;
        });
}


// Function to update the income chart
function updateIncomeChart(unitData) {
    // Destroy existing chart if it exists
    if (window.incomeByUnitChart instanceof Chart) {
        window.incomeByUnitChart.destroy();
    }

    const ctx = document.getElementById('income-by-unit-chart').getContext('2d');

    // Prepare data for the chart
    const labels = unitData.map(item => item.unitNumber);
    const salesData = unitData.map(item => item.salesIncome);
    const profitData = unitData.map(item => item.netProfit);

    // Create the chart
    window.incomeByUnitChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Sales Income',
                    data: salesData,
                    backgroundColor: '#6BBBFA',
                    borderColor: '#6BBBFA',
                    borderWidth: 1
                },
                {
                    label: 'Net Profit',
                    data: profitData,
                    backgroundColor: '#66BB8A',
                    borderColor: '#66BB8A',
                    borderWidth: 1
                }
            ]
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: {
                    ticks: {
                        callback: function(value) {
                            return 'RM ' + value;
                        }
                    }
                }
            },
            plugins: {
                legend: {
                    position: 'top',
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            let label = context.dataset.label || '';
                            if (label) {
                                label += ': RM';
                            }
                            if (context.parsed.x !== null) {
                                label += context.parsed.x.toFixed(2);
                            }
                            return label;
                        }
                    }
                }
            }
        }
    });
}

// Function to update the income table
function updateIncomeTable(unitData, sortConfig = { field: 'netProfit', direction: 'desc' }) {
    const tableBody = document.getElementById('income-table-body');
    tableBody.innerHTML = '';

    // Apply sorting
    unitData.sort((a, b) => {
        let aValue = a[sortConfig.field];
        let bValue = b[sortConfig.field];

        // For string values like unitNumber
        if (typeof aValue === 'string') {
            aValue = aValue.toLowerCase();
            bValue = bValue.toLowerCase();
        }

        if (sortConfig.direction === 'asc') {
            return aValue < bValue ? -1 : (aValue > bValue ? 1 : 0);
        } else {
            return aValue > bValue ? -1 : (aValue < bValue ? 1 : 0);
        }
    });

    let totalSalesIncome = 0;
    let totalNetProfit = 0;

    // Add rows for each unit
    unitData.forEach(item => {
        totalSalesIncome += item.salesIncome;
        totalNetProfit += item.netProfit;

        const row = document.createElement('tr');

        const unitCell = document.createElement('td');
        unitCell.textContent = item.unitNumber;
        row.appendChild(unitCell);

        const salesCell = document.createElement('td');
        salesCell.textContent = formatCurrency(item.salesIncome);
        row.appendChild(salesCell);

        const profitCell = document.createElement('td');
        profitCell.textContent = formatCurrency(item.netProfit);
        profitCell.style.color = item.netProfit >= 0 ? '#28a745' : '#dc3545';
        row.appendChild(profitCell);

        const marginCell = document.createElement('td');
        marginCell.textContent = item.profitMargin.toFixed(1) + '%';
        marginCell.style.color = item.profitMargin >= 0 ? '#28a745' : '#dc3545';
        row.appendChild(marginCell);

        tableBody.appendChild(row);
    });

    // Update totals
    document.getElementById('total-sales-income').textContent = formatCurrency(totalSalesIncome);

    const totalProfitElement = document.getElementById('total-net-profit');
    totalProfitElement.textContent = formatCurrency(totalNetProfit);
    totalProfitElement.style.color = totalNetProfit >= 0 ? '#28a745' : '#dc3545';

    const totalMargin = totalSalesIncome > 0 ? (totalNetProfit / totalSalesIncome) * 100 : 0;
    const totalMarginElement = document.getElementById('total-profit-margin');
    totalMarginElement.textContent = totalMargin.toFixed(1) + '%';
    totalMarginElement.style.color = totalMargin >= 0 ? '#28a745' : '#dc3545';

    // Update header sorting indicators
    updateSortingIndicators(sortConfig);
}

// Global variable to store current sort state
let currentIncomeSort = { field: 'netProfit', direction: 'desc' };
let currentIncomeData = [];

// Function to handle header clicks for sorting
function setupIncomeSorting() {
    const headers = document.querySelectorAll('#income-table-container th');

    // Map headers to their respective data fields
    const headerFields = {
        0: 'unitNumber',
        1: 'salesIncome',
        2: 'netProfit',
        3: 'profitMargin'
    };

    // Add click handlers to headers
    headers.forEach((header, index) => {
        if (index < Object.keys(headerFields).length) { // Skip if not in our mapping
            header.style.cursor = 'pointer';

            // Add subtle indicator that it's clickable
            header.title = 'Click to sort';

            // Add a sort indicator span
            if (!header.querySelector('.sort-indicator')) {
                const indicator = document.createElement('span');
                indicator.className = 'sort-indicator';
                indicator.style.marginLeft = '5px';
                indicator.innerHTML = '';
                header.appendChild(indicator);
            }

            header.addEventListener('click', function() {
                const field = headerFields[index];

                // Toggle direction if same field, otherwise default to ascending
                if (currentIncomeSort.field === field) {
                    currentIncomeSort.direction = currentIncomeSort.direction === 'asc' ? 'desc' : 'asc';
                } else {
                    currentIncomeSort.field = field;
                    currentIncomeSort.direction = 'asc';
                }

                // Update table with new sort
                updateIncomeTable(currentIncomeData, currentIncomeSort);
            });
        }
    });
}

// Function to update sorting indicators
function updateSortingIndicators(sortConfig) {
    const headers = document.querySelectorAll('#income-table-container th');
    const headerFields = {
        0: 'unitNumber',
        1: 'salesIncome',
        2: 'netProfit',
        3: 'profitMargin'
    };

    // Clear all indicators
    headers.forEach(header => {
        const indicator = header.querySelector('.sort-indicator');
        if (indicator) {
            indicator.innerHTML = '';
        }
    });

    // Set the active indicator
    for (let i = 0; i < headers.length; i++) {
        if (headerFields[i] === sortConfig.field) {
            const indicator = headers[i].querySelector('.sort-indicator');
            if (indicator) {
                indicator.innerHTML = sortConfig.direction === 'asc' ? ' ▲' : ' ▼';
            }
            break;
        }
    }
}

// Helper function to format currency values
function formatCurrency(value) {
    return new Intl.NumberFormat('en-MY', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    }).format(value);
}

// Update the existing code that handles tab switching in the DOMContentLoaded event
document.addEventListener('DOMContentLoaded', function() {
    // ... existing code ...

    // Initialize Income by Unit Analysis
    initializeIncomeByUnitAnalysis();

    // Modify the existing event listener for analysis options
    const analysisOptions = document.querySelectorAll('.analysis-option');
    if (analysisOptions.length > 0) {
        analysisOptions.forEach(option => {
            option.addEventListener('click', function() {
                // Remove active class from all options
                analysisOptions.forEach(opt => opt.classList.remove('active'));

                // Add active class to clicked option
                this.classList.add('active');

                // Get the analysis type
                const analysisType = this.getAttribute('data-analysis');

                // Hide all analysis content
                document.querySelector('.analysis-content').style.display = 'none';
                document.querySelector('.pl-statement-content').style.display = 'none';
                document.querySelector('.yoy-comparison-content').style.display = 'none';
                document.querySelector('.roi-analysis-content').style.display = 'none';
                document.querySelector('.income-by-unit-content').style.display = 'none';

                // Show the selected analysis content
                if (analysisType === 'expenses-breakdown') {
                    document.querySelector('.analysis-content').style.display = 'block';
                    updateAnalysis(); // Refresh the data
                } else if (analysisType === 'pl-statement') {
                    document.querySelector('.pl-statement-content').style.display = 'block';
                    updatePnLStatement(); // Refresh the data
                } else if (analysisType === 'yoy-comparison') {
                    document.querySelector('.yoy-comparison-content').style.display = 'block';
                    updateYoYComparison(); // Load the YoY comparison data
                } else if (analysisType === 'roi-analysis') {
                    document.querySelector('.roi-analysis-content').style.display = 'block';
                    updateROIAnalysis(); // Load the ROI analysis data
                } else if (analysisType === 'income-by-unit') {
                    document.querySelector('.income-by-unit-content').style.display = 'block';
                    updateIncomeByUnitAnalysis(); // Load the Income by Unit data
                }
            });
        });
    }

    // Also update these listeners to handle the new tab
    document.getElementById('analysis-month-year')?.addEventListener('change', function() {
        const activeOption = document.querySelector('.analysis-option.active');
        if (activeOption) {
            const analysisType = activeOption.getAttribute('data-analysis');
            if (analysisType === 'roi-analysis') {
                updateROIAnalysis();
            } else if (analysisType === 'income-by-unit') {
                updateIncomeByUnitAnalysis();
            } else if (analysisType === 'pl-statement') {
                updatePnLStatement();
            } else if (analysisType === 'yoy-comparison') {
                updateYoYComparison();
            } else {
                updateAnalysis();
            }
        }
    });

    document.getElementById('analysis-unit')?.addEventListener('change', function() {
        const activeOption = document.querySelector('.analysis-option.active');
        if (activeOption) {
            const analysisType = activeOption.getAttribute('data-analysis');
            if (analysisType === 'roi-analysis') {
                updateROIAnalysis();
            } else if (analysisType === 'income-by-unit') {
                updateIncomeByUnitAnalysis();
            } else if (analysisType === 'pl-statement') {
                updatePnLStatement();
            } else if (analysisType === 'yoy-comparison') {
                updateYoYComparison();
            } else {
                updateAnalysis();
            }
        }
    });
});