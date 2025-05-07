from django.shortcuts import render

# Create your views here.
import pandas as pd
import numpy as np
import requests
from io import BytesIO
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.ensemble import RandomForestRegressor
from rest_framework.views import APIView
from rest_framework.response import Response
from django.http import FileResponse
import os
from django.conf import settings

class InvestmentSimulationView(APIView):
    def post(self, request):
        try:
            # === Get inputs from frontend ===
            monthly_investment = int(request.data['monthly_investment'])
            investment_years = int(request.data['investment_years'])
            bond_tenor_years = int(request.data['bond_tenor_years'])
            start_year = int(request.data['start_year'])
            start_month = int(request.data['start_month'])

            # === Step 1: Load Excel from Google Drive ===
            file_id = "1uBNpotluswG-Z5m2zqTo-7ibG1gB99Vs"
            url = f"https://drive.google.com/uc?export=download&id={file_id}"
            response = requests.get(url)
            df = pd.read_excel(BytesIO(response.content))

            # === Step 2: Train Model ===
            df = df[["Year", "Month", "Tenor (Years)", "Weighted Avg Yield (%)"]].dropna()
            df.columns = ["Year", "Month", "Tenor", "Yield"]
            X = df[["Year", "Month", "Tenor"]]
            y = df["Yield"]

            preprocessor = ColumnTransformer([
                ("num", StandardScaler(), ["Year"]),
                ("cat", OneHotEncoder(handle_unknown="ignore"), ["Month", "Tenor"])
            ])

            model = Pipeline([
                ("preprocessor", preprocessor),
                ("regressor", RandomForestRegressor(n_estimators=200, random_state=42))
            ])
            model.fit(X, y)

            # === Step 3: Simulation ===
            investment_months = investment_years * 12
            total_months = investment_months + bond_tenor_years * 12
            investment_batches = []
            records = []
            cumulative_invested = 0

            for i in range(total_months):
                month_index = i + 1
                year = start_year + ((start_month - 1 + i) // 12)
                cal_month = ((start_month - 1 + i) % 12) + 1

                interest_earned = 0
                matured_principal = 0
                new_investment = 0
                annual_yield = None
                semi_annual_rate = None

                if month_index <= investment_months:
                    annual_yield = model.predict(pd.DataFrame([[year, cal_month, bond_tenor_years]],
                                                               columns=["Year", "Month", "Tenor"]))[0]
                    semi_annual_rate = annual_yield / 2 / 100

                    for batch in investment_batches:
                        age = month_index - batch["month"]
                        if age > 0 and age % 6 == 0 and age <= bond_tenor_years * 12:
                            interest_earned += batch["amount"] * batch["rate"]

                    new_investment = monthly_investment + interest_earned
                    investment_batches.append({
                        "month": month_index,
                        "amount": new_investment,
                        "rate": semi_annual_rate
                    })
                    cumulative_invested += new_investment
                else:
                    for batch in investment_batches:
                        age = month_index - batch["month"]
                        if age > 0 and age % 6 == 0 and age <= bond_tenor_years * 12:
                            interest_earned += batch["amount"] * batch["rate"]
                        if age == bond_tenor_years * 12:
                            matured_principal += batch["amount"]

                records.append({
                    "Month": month_index,
                    "Year": year,
                    "Calendar Month": cal_month,
                    "Predicted Annual Yield (%)": round(annual_yield, 3) if annual_yield else "",
                    "Semi-Annual Rate": round(semi_annual_rate, 5) if semi_annual_rate else "",
                    "New Investment (ZMW)": round(new_investment, 2),
                    "Cumulative Investment (ZMW)": round(cumulative_invested, 2),
                    "Interest Earned (Coupon)": round(interest_earned, 2),
                    "Matured Principal": round(matured_principal, 2)
                })

            # Summary
            total_investment = sum(
                r["New Investment (ZMW)"] for r in records if isinstance(r["New Investment (ZMW)"], (int, float)))
            total_interest = sum(r["Interest Earned (Coupon)"] for r in records if
                                 isinstance(r["Interest Earned (Coupon)"], (int, float)))

            file_name = f"Bond_{investment_years}Y_Investment_{bond_tenor_years}Y_Coupon_Simulation.xlsx"
            df_out = pd.DataFrame(records)

            # Save in /reports folder
            excel_path = os.path.join(settings.REPORTS_DIR, file_name)
            df_out.to_excel(excel_path, index=False)

            # Generate accessible URL for the frontend
            excel_url = f"http://{request.get_host()}/reports/{file_name}"

            return Response({
                "summary": {
                    "total_invested": round(total_investment, 2),
                    "total_interest": round(total_interest, 2),
                    "duration_months": total_months,
                    "excel_url": excel_url
                },
                "records": records
            })


        except Exception as e:
            return Response({"error": str(e)}, status=500)

class DownloadExcelView(APIView):
    def get(self, request):
        file_path = "Bond_3Y_Investment_5Y_Coupon_Simulation.xlsx"  # Adjust to dynamic later
        if os.path.exists(file_path):
            return FileResponse(open(file_path, 'rb'), as_attachment=True, filename=os.path.basename(file_path))
        return Response({"error": "File not found"}, status=404)
