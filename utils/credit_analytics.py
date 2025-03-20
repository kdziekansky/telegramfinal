"""
Moduł do analizy wykorzystania kredytów - adapter dla Supabase
"""
import io
import matplotlib.pyplot as plt
import numpy as np
import datetime
import pytz
from matplotlib.dates import DateFormatter
from database.supabase_client import get_credit_transactions, get_credit_usage_by_type, get_user_credits

def generate_credit_usage_chart(user_id, days=30):
    """Generuje wykres użycia kredytów w czasie"""
    transactions = get_credit_transactions(user_id, days)
    
    if not transactions:
        return None
    
    # Dalej kod pozostaje ten sam - tylko źródło danych jest inne
    # Przygotuj dane do wykresu
    dates = []
    balances = []
    usage_amounts = []
    purchase_amounts = []
    
    for trans in transactions:
        try:
            # Konwersja formatu daty
            created_at = trans['created_at']
            if isinstance(created_at, str):
                dt = datetime.datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            else:
                dt = created_at
                
            dates.append(dt)
            balances.append(trans['credits_after'])
            
            if trans['transaction_type'] == 'deduct':
                usage_amounts.append(trans['amount'])
                purchase_amounts.append(0)
            elif trans['transaction_type'] in ['add', 'purchase']:
                usage_amounts.append(0)
                purchase_amounts.append(trans['amount'])
        except Exception as e:
            print(f"Błąd przy przetwarzaniu transakcji: {e}")
    
    # Reszta kodu wykresów bez zmian
    plt.figure(figsize=(10, 6))
    
    # Wykres salda
    plt.subplot(2, 1, 1)
    plt.plot(dates, balances, 'b-', label='Saldo kredytów')
    plt.xlabel('Data')
    plt.ylabel('Kredyty')
    plt.title('Historia salda kredytów')
    plt.grid(True, linestyle='--', alpha=0.7)
    plt.gca().xaxis.set_major_formatter(DateFormatter('%d-%m-%Y'))
    plt.gcf().autofmt_xdate()
    plt.legend()
    
    # ...reszta kodu generowania wykresu...
    
    # Zapisz wykres do bufora
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=100)
    buf.seek(0)
    plt.close()
    
    return buf

def get_credit_usage_breakdown(user_id, days=30):
    """Pobiera rozkład zużycia kredytów według rodzaju operacji"""
    return get_credit_usage_by_type(user_id, days)

def generate_usage_breakdown_chart(user_id, days=30):
    """Generuje wykres kołowy rozkładu zużycia kredytów"""
    usage_breakdown = get_credit_usage_breakdown(user_id, days)
    
    if not usage_breakdown:
        return None
    
    # Reszta kodu generowania wykresu bez zmian
    plt.figure(figsize=(8, 6))
    
    labels = list(usage_breakdown.keys())
    sizes = list(usage_breakdown.values())
    colors = ['#ff9999', '#66b3ff', '#99ff99', '#ffcc99', '#c2c2f0']
    
    plt.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%', startangle=90, shadow=True)
    plt.axis('equal')
    plt.title(f'Rozkład zużycia kredytów w ostatnich {days} dniach')
    
    # Zapisz wykres do bufora
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=100)
    buf.seek(0)
    plt.close()
    
    return buf

def predict_credit_depletion(user_id, days=30):
    """Przewiduje, kiedy skończą się kredyty użytkownika"""
    transactions = get_credit_transactions(user_id, days)
    current_balance = get_user_credits(user_id)
    
    if not transactions:
        return {"days_left": None, "average_daily_usage": 0, "current_balance": current_balance}
    
    # Oblicz całkowite zużycie w okresie
    total_usage = sum(trans['amount'] for trans in transactions if trans['transaction_type'] == 'deduct')
    average_daily_usage = total_usage / days
    
    if average_daily_usage <= 0:
        return {"days_left": None, "average_daily_usage": 0, "current_balance": current_balance}
    
    days_left = int(current_balance / average_daily_usage)
    depletion_date = datetime.datetime.now() + datetime.timedelta(days=days_left)
    
    return {
        "days_left": days_left,
        "depletion_date": depletion_date.strftime("%d.%m.%Y"),
        "average_daily_usage": round(average_daily_usage, 2),
        "current_balance": current_balance
    }