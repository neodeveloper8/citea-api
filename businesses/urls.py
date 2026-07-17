from rest_framework.routers import DefaultRouter

from .views import BusinessViewSet, CategoryViewSet, ServiceViewSet

router = DefaultRouter()
router.register("categories", CategoryViewSet, basename="category")
router.register("businesses", BusinessViewSet, basename="business")
router.register("services", ServiceViewSet, basename="service")

urlpatterns = router.urls
