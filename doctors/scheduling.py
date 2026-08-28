from datetime import datetime, timedelta

from django.utils import timezone

SLOT_LENGTH = timedelta(minutes=30)


def within_hours(doctor, day, start):
    """Require the whole appointment, not just its start, to fit working hours."""
    schedule = doctor.availability.filter(weekday=day.weekday()).first()
    if schedule is None:
        return False
    begins = datetime.combine(day, start)
    return (datetime.combine(day, schedule.start_time) <= begins
            and begins + SLOT_LENGTH <= datetime.combine(day, schedule.end_time))


def available_slots(doctor, day):
    from billing.services import expire_holds
    expire_holds()
    schedule = doctor.availability.filter(weekday=day.weekday()).first()
    if schedule is None:
        return []
    from appointments.models import Appointment
    occupied = set(Appointment.objects.filter(doctor=doctor, appointment_date=day).exclude(
        status=Appointment.Status.CANCELLED).values_list("appointment_time", flat=True))
    current = datetime.combine(day, schedule.start_time)
    closing = datetime.combine(day, schedule.end_time)
    slots = []
    while current + SLOT_LENGTH <= closing:
        if current.time() not in occupied and timezone.make_aware(current) > timezone.now():
            slots.append(current.strftime("%H:%M"))
        current += SLOT_LENGTH
    return slots
