from django.shortcuts import render, redirect, get_object_or_404
from .models import Department
from .forms import DepartmentForm


def department_list(request):
    departments = Department.objects.all()

    context = {
        "departments": departments
    }

    return render(request, "departments/department_list.html", context)


def department_detail(request, id):
    department = get_object_or_404(Department, id=id)

    context = {
        "department": department
    }

    return render(request, "departments/department_detail.html", context)


def department_create(request):

    if request.method == "POST":

        form = DepartmentForm(request.POST)

        if form.is_valid():
            form.save()
            return redirect("department_list")

    else:
        form = DepartmentForm()

    context = {
        "form": form
    }

    return render(request, "departments/department_form.html", context)