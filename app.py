import mysql.connector
from flask import Flask, render_template, request, redirect, url_for, Response
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg') 
import matplotlib.pyplot as plt
import io
import base64

app = Flask(__name__)

# --- 1. ENCAPSULATION & HAS-A RELATIONSHIP ---
class DatabaseConnector:
    def __init__(self):
        self.conn = None
        self.cursor = None
        try:
            self.conn = mysql.connector.connect(
                host="localhost",
                user="root",
                password="*****", 
                database="inventory_db",
                port="3310"
            )
            self.cursor = self.conn.cursor(dictionary=True)
        except Exception as e:
            print(f"Database Connection Error: {e}")

# --- 2. INHERITANCE (IS-A) & POLYMORPHISM ---
class Product:
    def __init__(self, id, name, category, qty, price):
        self.id = id
        self.name = name
        self.category = category
        self.qty = qty if qty >= 0 else 0 
        self.price = price if price >= 0 else 0.0

    def get_total_value(self):
        return round(self.qty * self.price, 2)

class Electronics(Product):
    def get_total_value(self):
        return round((self.qty * self.price) * 1.10, 2)

class Perishable(Product):
    def get_total_value(self):
        return round((self.qty * self.price) * 0.95, 2)

# --- 3. ABSTRACTION & COMPOSITION ---
class InventoryManager:
    def __init__(self):
        self.db = DatabaseConnector()

    def get_all_products(self):
        if not self.db.cursor: return []
        self.db.cursor.execute("SELECT * FROM products")
        rows = self.db.cursor.fetchall()
        
        products = []
        for r in rows:
            cat = r['category'].lower()
            if 'elec' in cat:
                products.append(Electronics(r['id'], r['name'], r['category'], r['quantity'], r['price']))
            elif 'food' in cat or 'perish' in cat:
                products.append(Perishable(r['id'], r['name'], r['category'], r['quantity'], r['price']))
            else:
                products.append(Product(r['id'], r['name'], r['category'], r['quantity'], r['price']))
        return products

    def get_grand_total(self):
        prods = self.get_all_products()
        if not prods: return 0.0
        values = np.array([p.get_total_value() for p in prods])
        return np.sum(values)

    def add_product(self, name, cat, qty, price):
        if not self.db.cursor: return
        self.db.cursor.execute("SELECT id, quantity FROM products WHERE LOWER(name) = LOWER(%s)", (name,))
        existing = self.db.cursor.fetchone()

        if existing:
            new_qty = existing['quantity'] + int(qty)
            self.db.cursor.execute("UPDATE products SET quantity=%s, price=%s WHERE id=%s", (new_qty, price, existing['id']))
        else:
            self.db.cursor.execute("INSERT INTO products (name, category, quantity, price) VALUES (%s, %s, %s, %s)", (name, cat, qty, price))
        self.db.conn.commit()

    def get_analytics_plot(self, chart_type='bar'):
        prods = self.get_all_products()
        if not prods: return None
        df = pd.DataFrame([vars(p) for p in prods])
        df['total_val'] = np.array([p.get_total_value() for p in prods])

        plt.figure(figsize=(8, 4))
        colors = ['#6c5ce7', '#00b894', '#fab1a0', '#fdcb6e', '#e17055']

        if chart_type == 'pie':
            plt.pie(df['total_val'], labels=df['name'], autopct='%1.1f%%', colors=colors)
        elif chart_type == 'hist':
            plt.hist(df['total_val'], bins=5, color='#0984e3', edgecolor='white')
        else:
            plt.bar(df['name'], df['total_val'], color=colors[:len(df)])

        buf = io.BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight')
        plt.close()
        return base64.b64encode(buf.getvalue()).decode()

    def delete_product(self, p_id):
        if not self.db.cursor: return
        self.db.cursor.execute("DELETE FROM products WHERE id = %s", (p_id,))
        self.db.conn.commit()

manager = InventoryManager()

# --- 4. ROUTES ---
@app.route('/')
def index():
    chart_type = request.args.get('chart', 'bar')
    return render_template('index.html', 
                           products=manager.get_all_products(), 
                           chart=manager.get_analytics_plot(chart_type),
                           current_chart=chart_type,
                           grand_total=manager.get_grand_total())

@app.route('/add', methods=['POST'])
def add():
    manager.add_product(request.form.get('name'), request.form.get('category'),
                        int(request.form.get('qty', 0)), float(request.form.get('price', 0)))
    return redirect(url_for('index'))

@app.route('/delete/<int:id>')
def delete(id):
    manager.delete_product(id)
    return redirect(url_for('index'))

@app.route('/export')
def export_csv():
    """Uses Pandas to create a CSV from the current inventory objects"""
    prods = manager.get_all_products()
    if not prods:
        return redirect(url_for('index'))
    
    # Create a list of dictionaries including the polymorphic calculated values
    data = []
    for p in prods:
        data.append({
            "ID": p.id,
            "Name": p.name,
            "Category": p.category,
            "Quantity": p.qty,
            "Unit Price": p.price,
            "Adjusted Total Value": p.get_total_value()
        })
    
    df = pd.DataFrame(data)
    csv_data = df.to_csv(index=False)
    
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=inventory_report.csv"}
    )

if __name__ == '__main__':
    app.run(debug=True)