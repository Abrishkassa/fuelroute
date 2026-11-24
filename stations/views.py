from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .routing import RoutingError
from .services import LocationError, NoFeasibleRoute, plan_trip


class RouteQuerySerializer(serializers.Serializer):
    start = serializers.CharField(help_text="'City, ST' or 'lat,lng'")
    finish = serializers.CharField(help_text="'City, ST' or 'lat,lng'")
    start_fuel_miles = serializers.FloatField(required=False, min_value=0, max_value=500)
    corridor_miles = serializers.FloatField(required=False, min_value=1, max_value=50)


class RouteView(APIView):
    """GET /api/route/?start=Dallas, TX&finish=Atlanta, GA"""

    def get(self, request):
        params = RouteQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        try:
            data = params.validated_data
            return Response(plan_trip(
                data["start"], data["finish"],
                start_fuel_miles=data.get("start_fuel_miles"),
                corridor_miles=data.get("corridor_miles"),
            ))
        except LocationError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except NoFeasibleRoute as exc:
            return Response({"error": str(exc)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        except RoutingError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
